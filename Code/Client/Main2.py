# -*- coding: utf-8 -*-
"""
Licensed under CC BY-NC-SA 3.0

Derived from Freenove by Kenji Saito (ks91), 2025.

A version of Main.py that takes input from REST API instead of
GUI events. It is assumed that the robot has been set up using
the original Main.py client software.
"""

import sys
sys.path.append("../Server")

from flask import Flask, request, jsonify, g, send_file
from Video import *
from Command import COMMAND as cmd
import threading
import time


DEFAULT_MOVE_SPEED = '8'

FILENAME_IMAGE = 'image.jpg'

PORT_INSTRUCTIONS = 5003
PORT_VIDEO = 8003


class ClientService:
    def __init__(self):
        self.client = VideoStreaming()
        self.move_speed = DEFAULT_MOVE_SPEED
        
        try:
            with open('IP.txt', 'r') as file:
                self.ip_address = file.readline().strip()

        except FileNotFoundError:
            self.ip_address = '127.0.0.1'

        self.video_thread = None
        self.video_timer_thread = None
        self.instruction_thread = None
        self.connected = False
        self.distance = '0.00cm'
        self.arm_angle = 150
        self.grapple_angle = 90


    def receive_instructions(self):
        self.client.socket1_connect(self.ip_address)

        restCmd = ''
        while self.client.connect_Flag:
            Alldata = restCmd + str(self.client.recvData())
            restCmd = ''
            if Alldata == '':
                break
            else:
                cmdArray = Alldata.split('\n')
                if len(cmdArray) > 1 and cmdArray[-1] != '':
                    restCmd = cmdArray[-1]
                    cmdArray = cmdArray[:-1]
            for oneCmd in cmdArray:
                message = oneCmd.split('#')
                if cmd.CMD_SONIC in message:
                    self.distance = message[1]


    # Function to enable image input periodically
    def refresh_image(self):
        while self.connected:
            if self.client.video_Flag == False:
                self.client.video_Flag = True
            time.sleep(0.1)


def abort_by_bad_content_type(content_type):
    abort(400, description='Content-Type {0} is not expected'.format(
            content_type))


def abort_by_bad_json_format():
    abort(400, description='Bad JSON format')


def abort_by_missing_param(param):
    abort(400, description='{0} is missing'.format(param))


app = Flask(__name__)
service = ClientService()


@app.after_request
def after_request(response):
    return response


@app.before_request
def before_request():
    global service
    g.service = service


# Endpoint to connect
@app.route('/connect', methods=['POST'])
def connect_robot():
    if not g.service.connected:
        g.service.client.StartTcpClient(g.service.ip_address)
        g.service.client.StartTcpClient1(g.service.ip_address)
        g.service.connected = True

        # Start video and instruction threads
        g.service.video_thread = threading.Thread(
                target=g.service.client.streaming,
                args=(g.service.ip_address,))
        g.service.video_timer_thread = threading.Thread(
                target=g.service.refresh_image)
        g.service.instruction_thread = threading.Thread(
                target=g.service.receive_instructions)
        g.service.video_thread.start()
        g.service.video_timer_thread.start()
        g.service.instruction_thread.start()

        return jsonify({'status': 'Connected'}), 200


# Endpoint to disconnect
@app.route('/disconnect', methods=['POST'])
def disconnect_robot():
    if g.service.connected:
        try:
            g.service.client.client_socket1.close()
            g.service.client.connect_Flag = False

        except Exception as e:
            print('Error disconnecting: ', e)

        g.service.connected = False
        g.service.client.StopTcpcClient()
        g.service.client.StopTcpcClient1()

        return jsonify({'status': 'Disconnected'}), 200


# End point to move or stop
@app.route('/stop', methods=['POST'])
@app.route('/motor', methods=['POST'])
@app.route('/motor/<string:right>/<string:left>', methods=['POST'])
def motor(right=None, left=None):
    if right is None:
        right = '0'
        left = '0'
    command = cmd.CMD_MOTOR + f'#{right}#{left}\n'
    g.service.client.sendData(command)
    return jsonify({
        'status': 'Moving',
        'right': int(right),
        'left': int(left)
    }), 200


# Endpoint to control the arm
@app.route('/arm', methods=['POST'])
@app.route('/arm/<string:target>', methods=['POST'])
def arm(target=None):
    if target is None:
        target = '150'
    target_angle = int(target)
    angle = g.service.arm_angle
    if angle < target_angle:
        while angle < target_angle:
            command = cmd.CMD_SERVO + f'#1#{angle}\n'
            g.service.client.sendData(command)
            g.service.arm_angle = angle
            angle += 4
            time.sleep(0.1)
    else:
        while angle > target_angle:
            command = cmd.CMD_SERVO + f'#1#{angle}\n'
            g.service.client.sendData(command)
            g.service.arm_angle = angle
            angle -= 4
            time.sleep(0.1)
    return jsonify({'status': 'Arm angle changed', 'angle': g.service.arm_angle}), 200


# Endpoint to control the grapple
@app.route('/grapple', methods=['POST'])
@app.route('/grapple/<string:target>', methods=['POST'])
def grapple(target=None):
    if target is None:
        target = '90'
    target_angle = int(target)
    angle = g.service.grapple_angle
    if angle < target_angle:
        while angle < target_angle:
            command = cmd.CMD_SERVO + f'#0#{angle}\n'
            g.service.client.sendData(command)
            g.service.grapple_angle = angle
            angle += 4
            time.sleep(0.1)
    else:
        while angle > target_angle:
            command = cmd.CMD_SERVO + f'#0#{angle}\n'
            g.service.client.sendData(command)
            g.service.grapple_angle = angle
            angle -= 4
            time.sleep(0.1)
    return jsonify({'status': 'Grapple angle changed', 'angle': g.service.grapple_angle}), 200


# Endpoint for sonic
@app.route('/sonic', methods=['GET'])
def sonic():
    distance = f'{g.service.distance}cm'
    return jsonify({'status': 'Sonic data requested', 'distance': distance}), 200


# Endpoint to set LED mode and color (mode - 0 : off, 1 to 5)
@app.route('/led', methods=['POST'])
@app.route('/led/<string:mode>/<string:red>/<string:green>/<string:blue>', methods=['POST'])
def set_led_color(mode=None, red=None, green=None, blue=None):
    if mode is None:
        mode = '0'
        red = '255'
        green = '255'
        blue = '255'
    command = cmd.CMD_LED + f'#{mode}#{red}#{green}#{blue}#\n'
    g.service.client.sendData(command)
    return jsonify({
        'status': 'LED color set',
        'r': int(red),
        'g': int(green),
        'b': int(blue)
    }), 200


# Endpoint to get image from camera
@app.route('/camera/image', methods=['GET'])
def get_image():
    cv2.imwrite(FILENAME_IMAGE, g.service.client.image)
    return send_file(FILENAME_IMAGE, mimetype='image/jpeg')


# Endpoint to set car mode
@app.route('/mode', methods=['POST'])
@app.route('/mode/<string:mode>', methods=['POST'])
def set_mode(mode=None):
    if mode is None:
        mode = '0'
    command = cmd.CMD_MODE + f'#{mode}\n'
    g.service.client.sendData(command)
    return jsonify({
        'status': 'Car mode set',
        'mode': int(mode)
    }), 200


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
def error_handler(e):
    return jsonify({'error': {
        'code': e.code,
        'name': e.name,
        'description': e.description,
    }}), e.code

@app.errorhandler(ValueError)
@app.errorhandler(KeyError)
def error_handler(e):
    return jsonify({'error': {
        'code': 400,
        'name': 'Bad Request',
        'description': str(e),
    }}), 400


# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True)


# end of Main2.py
