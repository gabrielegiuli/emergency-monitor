import argparse
import logging
import time
import cv2
import firebase_admin
import numpy as np
from tf_pose.estimator import TfPoseEstimator
from tf_pose.networks import get_graph_path, model_wh
from firebase_admin import db
from firebase_admin import storage
from datetime import datetime

logger = logging.getLogger('TfPoseEstimator-WebCam')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
fps_time = 0

def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")

if __name__ == '__main__':
    # parse command line arguments
    parser = argparse.ArgumentParser(description='tf-pose-estimation realtime webcam')
    parser.add_argument('--camera', type=int, default=0)

    parser.add_argument('--resize', type=str, default='0x0',
                        help='if provided, resize images before they are processed. default=0x0, Recommends : 432x368 or 656x368 or 1312x736 ')
    parser.add_argument('--resize-out-ratio', type=float, default=4.0,
                        help='if provided, resize heatmaps before they are post-processed. default=1.0')

    parser.add_argument('--model', type=str, default='mobilenet_thin', help='cmu / mobilenet_thin / mobilenet_v2_large / mobilenet_v2_small')
    parser.add_argument('--show-process', type=bool, default=False,
                        help='for debug purpose, if enabled, speed for inference is dropped.')
    
    parser.add_argument('--tensorrt', type=str, default="False",
                        help='for tensorrt process.')

    args = parser.parse_args()

    logger.debug('initialization %s : %s' % (args.model, get_graph_path(args.model)))
    w, h = model_wh(args.resize)
    
    # check for video dimension
    if w > 0 and h > 0:
        e = TfPoseEstimator(get_graph_path(args.model), target_size=(w, h), trt_bool=str2bool(args.tensorrt))
    else:
        e = TfPoseEstimator(get_graph_path(args.model), target_size=(232, 200), trt_bool=str2bool(args.tensorrt))
        
    logger.debug('cam read+')
    cam = cv2.VideoCapture(args.camera)
    ret_val, image = cam.read()
    logger.info('cam image=%dx%d' % (image.shape[1], image.shape[0]))

    # initialize variables
    y1 = [0, 0]
    fall_y_pos = 0
    fall_state = False
    trigger_video = False
    fall_duration = 0
    
    # initialize videosaver
    prev_time = datetime.now()
    prev_timestamp = prev_time.strftime("%d%b%Y%H%M%S")
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter(f'../saved/VIDEO{prev_timestamp}.avi', fourcc, 5, (image.shape[1],image.shape[0]))
    
    
    #########################################
    ### Database & Storage Initialization ###
    #########################################
    # extract user id
    with open('../../auth_key/user_id.txt') as f:
        userID = f.readlines()[0]
        
    # initialize database connection
    databaseURL = 'https://emergency-monitor-hz21-default-rtdb.europe-west1.firebasedatabase.app'
    cred_obj = firebase_admin.credentials.Certificate('../../auth_key/key.json')
    default_app = firebase_admin.initialize_app(cred_obj, {
        'databaseURL': databaseURL,
        'storageBucket': 'emergency-monitor-hz21.appspot.com'
    })
    
    # create database reference
    dbRef = db.reference("/users/" + userID + '/emergencies')
    
    # initialize storage bucket connection
    bucket = storage.bucket()
    
    # infinite while loop
    while True:
        ret_val, image = cam.read()
        logger.debug('image process+')
        humans = e.inference(image, resize_to_default=(w > 0 and h > 0), upsample_size=args.resize_out_ratio)
        
        # Fall Detection
        for human in humans:
            for i in range(len(humans)):
                try:
                    head_obj = human.body_parts[0]
                    x_head = head_obj.x*image.shape[1]
                    y_head = head_obj.y*image.shape[0]
        
                    y1.append(y_head)
                    y1.pop(0)
                    
                    # for initial appearance
                    if (y1[-2] == 0):
                        pass
                    
                    # detect initial fall
                    elif (y_head - y1[-2]) > 30 and not fall_state:
                        fall_state = True
                        trigger_video = True
                        fall_start = datetime.now()
                        fall_y_pos = y_head
                        
                    # detect if wake back up
                    elif (fall_y_pos - y_head) > 30:
                        fall_state = False
                        fall_y_pos = 0

                    # print fall detection
                    if fall_state:
                        cv2.putText(image, "Fall Detected", (10,30), cv2.FONT_HERSHEY_COMPLEX, 0.5, (0,0,255), 2, 11)
                        
                except:
                    pass

        logger.debug('postprocess+')
        image = TfPoseEstimator.draw_humans(image, humans, imgcopy=False)

        logger.debug('show+')
        cv2.imshow('tf-pose-estimation result', image)
        fps_time = time.time()
        
        # initialize videowriter
        if trigger_video:
            trigger_video = False
            cur_time = datetime.now()
            
            if (cur_time - prev_time).total_seconds() >= 60:
                # create new videowriter
                cur_timestamp = cur_time.strftime("%d%b%Y%H%M%S")
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                out = cv2.VideoWriter(f'../saved/VIDEO{cur_timestamp}.avi', fourcc, 5, (image.shape[1],image.shape[0]))
                
                # update prev time
                prev_time = cur_time
                prev_timestamp = cur_timestamp        
        
        # save video
        if fall_state:
            # write frame to video
            out.write(image)
            
            # if fall duration is >= 10s, send video for help
            cur_time = datetime.now()
            fall_duration = (cur_time - fall_start).total_seconds()
            
            print("FALL_DURATION: ", fall_duration)
            
            # trigger fall detection
            if fall_duration >= 5:
                fall_state = 0
                print("FALL DETECTED...")

                # Post request in firebase RTDB
                dbRef.push({
                    "timestamp": fall_start.strftime("%d-%b-%Y (%H:%M:%S.%f)"),
                    "type": "video",
                    "audioTranscript": "N/A"
                })
                
                # store blob on firebase storage
                blob = bucket.blob(f'{userID}/VIDEO{prev_timestamp}.avi')
                blob.upload_from_filename(f'../saved/VIDEO{prev_timestamp}.avi')
                
                
        if cv2.waitKey(1) == 27:
            break
        logger.debug('finished+')

    cv2.destroyAllWindows()
