source /home/songxm/anaconda3/bin/activate py310_face
nohup python app.py > /tmp/log.face_service 2>&1 &
conda deactivate
