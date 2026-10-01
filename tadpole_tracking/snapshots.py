"""Requested-time original frames and calibrated silhouette figure panels."""
import cv2
import numpy as np
import pandas as pd
from .frog import silhouette, posterior_width, SIZE, ORIGIN
from .arena import raw_to_mm
from .modes import hindlimb_enabled


def export_snapshots(video, raw_indices, body_table, axis_tracks, config, paths):
    times = config['output'].get('snapshot_times_s', [])
    if not times:
        return []
    from .plots import plt
    target_dir = paths['plots'].parent / 'snapshots'
    target_dir.mkdir(exist_ok=True)
    fps = config['video'].get('timebase_fps', config['video']['fps'])
    index = {int(frame): i for i, frame in enumerate(raw_indices)}
    width_path = paths['tables'] / '10_frog_hindlimb_silhouette.tsv'
    widths = pd.read_csv(width_path, sep='\t') if hindlimb_enabled(config) and width_path.exists() else None
    settings = config.get('frog_hindlimb', {})
    cal = config['dish_calibration']
    length = np.linalg.norm(np.diff(raw_to_mm(np.asarray(settings['axis_points_raw_px']), cal), axis=0)) if widths is not None else None
    cap = cv2.VideoCapture(str(video))
    manifest = []
    try:
        for order, requested in enumerate(times, 1):
            frame_number = int(np.floor(requested * fps + .5))
            frame_number = min(frame_number, config['video']['frame_count']-1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f'Cannot read snapshot frame {frame_number}')
            actual = frame_number / fps
            stem = f'{order:02d}_{actual:.3f}s_frame{frame_number}'
            cv2.imwrite(str(target_dir / f'{stem}_original.png'), frame)
            row = {'requested_time_s': requested, 'actual_time_s': actual, 'raw_frame': frame_number,
                   'hindlimb_silhouette_spread_mm': np.nan, 'hindlimb_silhouette_spread_cm': np.nan,
                   'measurement_status': 'not_tracked_frame', 'original_png': f'{stem}_original.png'}
            i = index.get(frame_number)
            item = None
            if widths is None:
                row['measurement_status'] = 'hindlimb_not_enabled'
            elif i is not None:
                row['measurement_status'] = 'excluded'
                if bool(widths.iloc[i].hindlimb_valid):
                    centre = body_table.iloc[i][['head_x_px', 'head_y_px']].to_numpy(float)
                    item = silhouette(frame, centre, axis_tracks[i], cal, settings, length)
                    if item is not None:
                        spread = float(widths.iloc[i].hindlimb_silhouette_spread_mm)
                        row.update(hindlimb_silhouette_spread_mm=spread, hindlimb_silhouette_spread_cm=spread/10,
                                   measurement_status='measured')
            fig, axes = plt.subplots(1, 2 if widths is not None else 1, figsize=(5.5 if widths is not None else 2.7, 3.3), squeeze=False)
            axes = axes[0]
            axes[0].imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB));axes[0].set_title(f'{actual:g} s', fontsize=10);axes[0].axis('off')
            if widths is not None:
                ax = axes[1]
                ax.set_xlim(0, SIZE);ax.set_ylim(SIZE+24, 0);ax.set_aspect('equal');ax.axis('off')
                if item is not None:
                    aligned, mask, _, scale = item
                    axes[0].images[0].set_data(cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB))
                    axes[0].images[0].set_extent((-.5,SIZE-.5,SIZE-.5,-.5))
                    axes[0].set_title(f'{actual:g} s · body aligned',fontsize=9)
                    cutoff = float(widths.iloc[i].fixed_posterior_cutoff_mm_from_body_reference)*scale+ORIGIN[1]
                    value = posterior_width(mask, cutoff, scale)
                    colored = np.ones((SIZE,SIZE,4));colored[mask.astype(bool)] = [0.93,0.43,0.16,1]
                    ax.imshow(colored)
                    ax.axhline(cutoff,color='#697586',ls=(0,(5,3)),lw=.6)
                    bottom = min(SIZE-8, max(np.where(mask)[0])+14)
                    for x in value[1:3]:ax.plot([x,x],[cutoff,bottom],color='#198bac',ls=(0,(3,3)),lw=.6)
                    ax.annotate('',xy=(value[1],bottom),xytext=(value[2],bottom),arrowprops={'arrowstyle':'<->','color':'#198bac','lw':.7})
                    ax.text(np.mean(value[1:3]),bottom+18,f"{row['hindlimb_silhouette_spread_cm']:.2f} cm",ha='center',va='top',fontsize=10)
                    ax.set_title('Posterior silhouette spread',fontsize=8)
                    ys,xs=np.where(mask)
                    for panel_axis in axes:
                        panel_axis.set_xlim(max(0,xs.min()-35),min(SIZE,xs.max()+35))
                        panel_axis.set_ylim(min(SIZE+24,bottom+38),max(0,ys.min()-12))
                else:
                    ax.text(.5,.5,'No valid measurement\nfor this frame',ha='center',va='center',transform=ax.transAxes,fontsize=8)
            fig.tight_layout(pad=.5)
            fig.savefig(target_dir / f'{stem}_panel.png',dpi=300,facecolor='white')
            fig.savefig(target_dir / f'{stem}_panel.pdf',facecolor='white')
            if widths is not None and item is not None:
                fig.canvas.draw()
                bounds=axes[1].get_tightbbox(fig.canvas.get_renderer()).transformed(fig.dpi_scale_trans.inverted()).expanded(1.04,1.04)
                for extension in ['png','pdf']:
                    fig.savefig(target_dir / f'{stem}_silhouette.{extension}',dpi=300,facecolor='white',bbox_inches=bounds)
            plt.close(fig)
            row['panel_png'] = f'{stem}_panel.png'
            manifest.append(row)
    finally:
        cap.release()
    pd.DataFrame(manifest).to_csv(paths['tables']/'12_requested_snapshots.tsv',sep='\t',index=False)
    pd.DataFrame(manifest).to_csv(paths['tables']/'12_requested_snapshots.csv',index=False)
    return manifest
