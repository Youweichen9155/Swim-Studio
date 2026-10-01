"""Generate a labelled test video; this is not biological validation data."""
from pathlib import Path
import sys
import cv2
import numpy as np

path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),30,(320,240))
if not writer.isOpened(): raise RuntimeError('Video encoder unavailable')
rng=np.random.default_rng(20)
background=np.full((240,320,3),225,np.uint8)
cv2.rectangle(background,(15,20),(305,220),(135,155,145),2)
texture=rng.integers(0,80,(25,25,3),np.uint8)
for i in range(48):
    frame=background.copy();x=80+i//2;y=110+i//6
    cv2.ellipse(frame,(x+5,y),(24,14),0,0,360,(100,115,95),-1)
    frame[y-12:y+13,x-12:x+13]=texture
    cv2.circle(frame,(x-6,y-6),3,(240,240,240),-1)
    cv2.circle(frame,(x-6,y+6),3,(240,240,240),-1)
    cv2.putText(frame,'SYNTHETIC TEST',(20,38),cv2.FONT_HERSHEY_SIMPLEX,.37,(70,70,70),1)
    writer.write(frame)
writer.release()
print(path)
