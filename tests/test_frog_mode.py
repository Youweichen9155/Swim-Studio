"""Frog geometry, exclusions, mode persistence and full exported outputs."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
import cv2
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tadpole_tracking.config import load_config, validate_config, ConfigError
from tadpole_tracking.modes import tracking_queries, frog_defaults
from tadpole_tracking.frog import silhouette, posterior_width
from tadpole_tracking.pipeline import run_analysis
from tadpole_tracking.gui_server import Application
from tadpole_tracking.inputs import save_tracking_cache


class FrogTests(unittest.TestCase):
    def setUp(self):
        self.path=ROOT/'examples/configs/tadpole_recording_001.json'
        self.config=load_config(self.path)
        self.config['animal_mode']='frog'
        self.config['frog_hindlimb']=dict(frog_defaults(),axis_points_raw_px=[[150,80],[150,145]])
        self.config['video'].update(fps=30.,frame_count=30,width_px=320,height_px=240,path='input.mp4')
        self.config['model_tracking'].update(roi_raw_px=[0,0,320,240],frame_step=1,cache_path='tracks.npz')
        self.config['head_point_selection'].update(query_points_raw_px=[[146,106],[154,106],[146,116],[154,116]],drop_query_indices=[],minimum_visible_points=2)
        self.config['dish_calibration']={'type':'rectangle','corners_raw_px':[[0,0],[319,0],[319,239],[0,239]],'width_mm':319.,'height_mm':239.}
        self.config['forceps_contact_review']['intervals_tsv']='contacts.tsv'
        self.config['output'].update(directory='results',make_video_qa=True,snapshot_times_s=[.1,.333])

    @staticmethod
    def frog_frame(spread=45):
        image=np.full((240,320,3),230,np.uint8)
        cv2.ellipse(image,(150,112),(20,35),0,0,360,(25,25,25),-1)
        for sign in [-1,1]:
            cv2.line(image,(150+sign*12,140),(150+sign*spread,180),(25,25,25),8)
        return image

    def test_width_known_pixel_quantiles(self):
        mask=np.zeros((100,100),np.uint8);mask[50:80,20:80]=1
        width,left,right,n=posterior_width(mask,49,2.)
        self.assertAlmostEqual(width,(76.05-22.95)/2)
        self.assertEqual(n,1800)

    def test_opening_is_larger_than_closing(self):
        cal=self.config['dish_calibration'];settings=self.config['frog_hindlimb']
        measurements=[]
        for spread in [15,45]:
            item=silhouette(self.frog_frame(spread),[150,112],[[150,80],[150,145]],cal,settings,65.)
            self.assertIsNotNone(item)
            measurements.append(posterior_width(item[1],item[2],item[3])[0])
        self.assertGreater(measurements[1],measurements[0]+20)

    def test_reject_bad_axis_and_modes(self):
        validate_config(self.config)
        for bad in [[],[[1,1],[1,1]],[[150,80],[999,99]]]:
            c=copy.deepcopy(self.config);c['frog_hindlimb']['axis_points_raw_px']=bad
            with self.assertRaises(ConfigError):validate_config(c)
        c=copy.deepcopy(self.config);c['animal_mode']='cat'
        with self.assertRaises(ConfigError):validate_config(c)

    def test_query_roles_and_disabled_hindlimb(self):
        self.assertEqual(tracking_queries(self.config).shape,(6,2))
        self.config['frog_hindlimb']['enabled']=False
        self.assertEqual(tracking_queries(self.config).shape,(4,2))
        self.config['animal_mode']='tadpole';self.config.pop('frog_hindlimb')
        self.assertEqual(tracking_queries(self.config).shape,(4,2))

    def test_frog_save_reload(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Path(d));key,_=app.create()
            p=app.initialize(key,'input.mp4',dict(width_px=320,height_px=240,raw_fps=30.,raw_frame_count=30),animal_mode='frog')
            c=copy.deepcopy(self.config)
            app.save(dict(id=key,config=c,intervals='start_s\tend_s\n',reviewed=True,calibration_reviewed=True))
            loaded=app.payload(key)['config']
            self.assertEqual(loaded['animal_mode'],'frog')
            self.assertEqual(loaded['frog_hindlimb']['axis_points_raw_px'],c['frog_hindlimb']['axis_points_raw_px'])

    def test_contact_does_not_pull_adjacent_body_positions(self):
        from tadpole_tracking.analysis import build_track_table
        points=tracking_queries(self.config)[:4]
        tracks=np.repeat(points[None],30,axis=0);tracks[10:15,:,0]+=100
        visible=np.ones((30,4),bool)
        audit=pd.DataFrame({'forceps_near_head':np.isin(np.arange(30),np.arange(10,15))})
        table=build_track_table(tracks,visible,np.arange(30),{'raw_fps':30.,'effective_fps':30.},audit,self.config)
        self.assertLess(np.nanmax(np.abs(table.head_x_mm_smooth-table.head_x_mm.iloc[0])),1e-6)
        self.assertFalse(table.loc[10:14,'analyzable'].any())

    def test_full_frog_outputs_exclude_contact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);video=root/'input.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),30.,(320,240))
            for i in range(30):writer.write(self.frog_frame(20+int(20*(1+np.sin(i/3))/2)))
            writer.release()
            (root/'contacts.tsv').write_text('start_s\tend_s\n0.3\t0.4\n')
            (root/'config.json').write_text(__import__('json').dumps(self.config))
            points=tracking_queries(self.config)
            tracks=np.repeat(points[None],30,axis=0);visible=np.ones((30,6),bool)
            # An occluded axis must not create an invented width.
            visible[20,4]=False
            metadata=dict(raw_fps=30.,raw_frame_count=30,width_px=320,height_px=240,effective_fps=30.)
            save_tracking_cache(root/'tracks.npz',tracks,visible,np.arange(30),points,metadata)
            out=run_analysis(self.config,root/'config.json',cache_only=True)
            self.assertEqual(out['summary']['animal_mode'],'frog')
            self.assertTrue((root/'results/tables/01_frame_level_body_trajectory.tsv').exists())
            table=pd.read_csv(root/'results/tables/10_frog_hindlimb_silhouette.tsv',sep='\t')
            self.assertFalse(table.loc[9:12,'hindlimb_valid'].any())
            self.assertFalse(table.loc[20,'hindlimb_valid'])
            self.assertFalse(out['table'].loc[9:12,'analyzable'].any())
            self.assertTrue(table.loc[0:8,'hindlimb_valid'].all())
            self.assertTrue((root/'results/video/frog_hindlimb_QA.mp4').exists())
            self.assertGreater(out['summary']['hindlimb_spread_p95_minus_p05_mm'],1.)
            chosen=pd.read_csv(root/'results/tables/12_requested_snapshots.csv')
            self.assertEqual(chosen.raw_frame.tolist(),[3,10])
            self.assertEqual(chosen.measurement_status.tolist(),['measured','excluded'])
            self.assertAlmostEqual(chosen.iloc[0].hindlimb_silhouette_spread_mm,table.iloc[3].hindlimb_silhouette_spread_mm)
            self.assertTrue((root/'results/snapshots'/chosen.iloc[0].original_png).exists())
            self.assertTrue((root/'results/snapshots'/chosen.iloc[0].panel_png).exists())


if __name__=='__main__':unittest.main(verbosity=2)
