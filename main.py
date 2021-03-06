"""People Counter."""
"""
 Copyright (c) 2018 Intel Corporation.
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit person to whom the Software is furnished to do so, subject to
 the following conditions:
 The above copyright notice and this permission notice shall be
 included in all copies or substantial portions of the Software.
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


import sys
import socket
import json
import cv2

import paho.mqtt.client as mqtt

from argparse import ArgumentParser
from inference import Network

# MQTT server environment variables
HOSTNAME = socket.gethostname()
IPADDRESS = socket.gethostbyname(HOSTNAME)
MQTT_HOST = IPADDRESS
MQTT_PORT = 3001
MQTT_KEEPALIVE_INTERVAL = 60


def build_argparser():
    """Parse command line arguments.

    :return: command line arguments
    """
    parser = ArgumentParser()
    parser.add_argument("-m", "--model", required=True, type=str,
                        help="Path to an xml file with a trained model.")
    parser.add_argument("-i", "--input", required=True, type=str,
                        help="Path to image or video file")
    parser.add_argument("-l", "--cpu_extension", required=False, type=str,
                        default=None,
                        help="MKLDNN (CPU)-targeted custom layers."
                             "Absolute path to a shared library with the"
                             "kernels impl.")
    parser.add_argument("-d", "--device", type=str, default="CPU",
                        help="Specify the target device to infer on: "
                             "CPU, GPU, FPGA or MYRIAD is acceptable. Sample "
                             "will look for a suitable plugin for device "
                             "specified (CPU by default)")
    parser.add_argument("-pt", "--prob_threshold", type=float, default=0.5,
                        help="Probability threshold for detections filtering"
                        "(0.5 by default)")
    return parser


def connect_mqtt():
    ### TODO: Connect to the MQTT client ###
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)
    return client


def infer_on_stream(args, client):
    """Initialize the inference network, stream video to network,
    and output stats and video.

    :param args: Command line arguments parsed by `build_argparser()`
    :param client: MQTT client
    :return: None
    """
    # Initialise the class
    infer_network = Network()
    # Set Probability threshold for detections
    prob_threshold = args.prob_threshold

    ### TODO: Load the model through `infer_network` ###
    infer_network.load_model(args.model, args.device, args.cpu_extension)
    net_input_shape = infer_network.get_input_shape()

    ### TODO: Handle the input stream ###
    # Create a flag for single images
    single_image_mode = False
    # Check if the input is a webcam
    if args.input == 'CAM':
        args.input = 0
    #Check if the input is an image
    elif args.input.endswith('.jpg') or args.input.endswith('.bmp'):
        single_image_mode = True
    
    capture = cv2.VideoCapture(args.input)
    capture.open(args.input)
    
    # Get the shape of the input
    width = int(capture.get(3))
    height = int(capture.get(4))

    # Initializing variables for counting
    duration = 0
    duration_prev = 0
    counter = 0
    counter_prev = 0
    counter_total = 0
    request_id = 0
    report = 0
     
    ### TODO: Loop until stream is over ###
    while capture.isOpened():
         ### TODO: Read from the video capture ###
        flag, frame = capture.read()
        if not flag:
            break

        ### TODO: Pre-process the image as needed ###
        p_frame = cv2.resize(frame, (net_input_shape[3], net_input_shape[2]))
        p_frame = p_frame.transpose((2,0,1))
        p_frame = p_frame.reshape(1, *p_frame.shape)
        
        ### TODO: Start asynchronous inference for specified request ###
        infer_network.exec_net(request_id, p_frame)    
        duration_report = 0
        
        ### TODO: Wait for the result ###
        if infer_network.wait() == 0:
            ### TODO: Get the results of the inference request ###
            net_output = infer_network.get_output()
            ### TODO: Extract any desired stats from the results ###
            people = 0
            probs = net_output[0, 0, :, 2]
            for i, p in enumerate(probs):
                if p > prob_threshold:
                    people += 1
                    box = net_output[0, 0, i, 3:]
                    p1 = (int(box[0] * width), int(box[1] * height))
                    p2 = (int(box[2] * width), int(box[3] * height))
                    frame = cv2.rectangle(frame, p1, p2, (0, 255, 0), 3)
        
            if people != counter:
                counter_prev = counter
                counter = people
                if duration >= 3:
                    duration_prev = duration
                    duration = 0
                else:
                    duration = duration_prev + duration
                    duration_prev = 0
            else:
                duration += 1
                if duration >= 3:
                    report = counter
                    if duration == 3 and counter > counter_prev:
                        counter_total += counter - counter_prev
                    elif duration == 3 and counter < counter_prev:
                        duration_report = int((duration_prev / 10.0) * 1000)
                      
            ### TODO: Calculate and send relevant information on ###
            ### current_count, total_count and duration to the MQTT server ###
            ### Topic "person": keys of "count" and "total" ###
            ### Topic "person/duration": key of "duration" ###
            client.publish('person', json.dumps({'count': report, 'total': \
                                                 counter_total}), 0, False)
            if duration_report != 0:
                client.publish('person/duration', json.dumps({'duration': \
                                                              duration_report}), \
                               0, False)            
            
        ### TODO: Send the frame to the FFMPEG server ###
        sys.stdout.buffer.write(frame)
        sys.stdout.flush()

        ### TODO: Write an output image if `single_image_mode` ###
        if single_image_mode:
            cv2.imwrite('output_image.jpg', frame)
            
    capture.release()
    cv2.destroyAllWindows()

def main():
    """
    Load the network and parse the output.

    :return: None
    """
    # Grab command line args
    args = build_argparser().parse_args()
    # Connect to the MQTT server
    client = connect_mqtt()
    # Perform inference on the input stream
    infer_on_stream(args, client)


if __name__ == '__main__':
    main()
