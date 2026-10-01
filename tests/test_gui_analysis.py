"""Portable scientific and application regression tests (no model/network needed)."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tadpole_tracking.arena import raw_to_mm, normalized_boundary, validate_arena
from tadpole_tracking.config import load_config, validate_config, ConfigError
from tadpole_tracking.pipeline import run_analysis
from tadpole_tracking.gui_server import Application


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.rect = {"type": "rectangle", "corners_raw_px": [[20, 30], [250, 20], [290, 190], [10, 210]], "width_mm": 200., "height_mm": 85.}

    def test_perspective_corners_and_center(self):
        validate_arena(self.rect)
        expected = [[-100, -42.5], [100, -42.5], [100, 42.5], [-100, 42.5]]
        np.testing.assert_allclose(raw_to_mm(np.asarray(self.rect["corners_raw_px"]), self.rect), expected, atol=1e-10)
        np.testing.assert_allclose(normalized_boundary(np.asarray(self.rect["corners_raw_px"]), self.rect), 1, atol=1e-10)

    def test_rectangle_known_distance_and_outside(self):
        r = dict(self.rect, corners_raw_px=[[10, 20], [410, 20], [410, 190], [10, 190]])
        points = np.array([[10, 20], [210, 105], [410, 190], [510, 105]])
        mm = raw_to_mm(points, r)
        np.testing.assert_allclose(mm[1], [0, 0], atol=1e-10)
        self.assertAlmostEqual(np.linalg.norm(mm[2]-mm[0]), np.hypot(200, 85))
        self.assertGreater(normalized_boundary(points, r)[-1], 1)

    def test_rotation_and_legacy_qc_remain_distinct(self):
        ellipse = {"type": "ellipse", "center_raw_px": [100, 100], "ellipse_diameters_px": [100, 50], "ellipse_angle_degrees": 90, "dish_diameter_mm": 100}
        xy = np.array([[100., 150.]])
        np.testing.assert_allclose(raw_to_mm(xy, ellipse), [[50, 0]], atol=1e-10)
        self.assertAlmostEqual(normalized_boundary(xy, ellipse)[0], 1)
        legacy = dict(ellipse, type="legacy_ellipse")
        self.assertAlmostEqual(normalized_boundary(xy, legacy)[0], 2)

    def test_bad_quadrilaterals(self):
        for corners in ([[0,0],[10,10],[0,10],[10,0]], [[0,0],[0,0],[10,10],[10,0]], [[0,0],[1,0],[2,0],[3,0]]):
            with self.assertRaises(ValueError):
                validate_arena(dict(self.rect, corners_raw_px=corners))
        with self.assertRaises(ValueError):
            validate_arena(dict(self.rect, width_mm=float('nan')))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_path = ROOT / "examples/configs/tadpole_recording_001.json"
        cls.config = load_config(cls.config_path)

    def test_frozen_metrics(self):
        with tempfile.TemporaryDirectory() as d:
            result = run_analysis(copy.deepcopy(self.config), self.config_path, output_override=Path(d), cache_only=True, skip_plots=True, skip_video_qa=True)
            expected = json.loads((ROOT / "tests/expected_metrics.json").read_text())
            for key, value in expected.items():
                with self.subTest(key=key):
                    self.assertAlmostEqual(result['summary'][key], value, delta=1e-9)
            self.assertFalse(result['provenance']['run']['model_was_run'])

    def test_rectangular_pipeline_and_plots(self):
        config = copy.deepcopy(self.config)
        config['dish_calibration'] = {"type":"rectangle", "corners_raw_px":[[550,170],[1400,170],[1400,1020],[550,1020]], "width_mm":200., "height_mm":85.}
        validate_config(config)
        with tempfile.TemporaryDirectory() as d:
            result = run_analysis(config, self.config_path, output_override=Path(d), cache_only=True, skip_video_qa=True)
            self.assertGreater(result['summary']['total_analyzable_distance_mm'], 0)
            self.assertEqual(result['summary']['arena_width_mm'], 200.)
            self.assertTrue((Path(d)/'plots/01_time_colored_swimming_trajectory.pdf').is_file())
            self.assertEqual(result['provenance']['configuration']['effective']['dish_calibration']['type'], 'rectangle')

    def test_timebase_override_and_provenance(self):
        config = copy.deepcopy(self.config)
        config['video']['timebase_fps'] = config['video']['fps'] * 2
        with tempfile.TemporaryDirectory() as d:
            result = run_analysis(config, self.config_path, output_override=Path(d), cache_only=True, skip_plots=True, skip_video_qa=True)
            self.assertAlmostEqual(result['table']['time_s'].iloc[-1], 4656/config['video']['timebase_fps'])
            self.assertEqual(result['summary']['encoded_fps'], config['video']['fps'])
            self.assertTrue(result['summary']['timebase_override'])
            # Frame-index contact membership remains fixed even when the clock changes.
            base = run_analysis(copy.deepcopy(self.config), self.config_path, output_override=Path(d)/'baseline', cache_only=True, skip_plots=True, skip_video_qa=True)
            np.testing.assert_array_equal(result['table']['forceps_near_head'], base['table']['forceps_near_head'])

    def test_reject_nonfinite_and_offscreen_parameters(self):
        config=copy.deepcopy(self.config)
        config['video']['fps']=float('nan')
        with self.assertRaises(ConfigError): validate_config(config)
        config=copy.deepcopy(self.config)
        config['head_point_selection']['query_points_raw_px'][0]=[0,0]
        with self.assertRaises(ConfigError): validate_config(config)


class ApplicationTests(unittest.TestCase):
    def test_demo_save_reload_and_owned_paths(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Path(d));demo=app.demo()
            self.assertEqual(len(app.projects()),1)
            config=demo['config']
            config['output']['directory']='../../escape'
            data=dict(id=demo['id'],config=config,intervals=demo['intervals'],reviewed=True,calibration_reviewed=True)
            saved=app.save(data)
            self.assertEqual(saved['config']['output']['directory'],'results')
            self.assertEqual(Application(Path(d)).payload(demo['id'])['config'],saved['config'])
            with self.assertRaises(ValueError):app.project('../escape')
            with self.assertRaises(ValueError):app.save(dict(data,reviewed=False))

    def test_demo_blocks_incompatible_cache_and_late_intervals(self):
        with tempfile.TemporaryDirectory() as d:
            app=Application(Path(d));demo=app.demo()
            data=dict(id=demo['id'],config=copy.deepcopy(demo['config']),intervals=demo['intervals'],reviewed=True,calibration_reviewed=True)
            data['config']['model_tracking']['frame_step']=2
            with self.assertRaises(ValueError):app.save(data)
            data['config']=demo['config'];data['intervals']='start_s\tend_s\n1\t9999\n'
            with self.assertRaises(ValueError):app.save(data)
            self.assertEqual(app.payload(demo['id'])['intervals'],demo['intervals'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
