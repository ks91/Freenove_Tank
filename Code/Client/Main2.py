# -*- coding: utf-8 -*-
"""
Licensed under CC BY-NC-SA 3.0

Derived from Freenove by Kenji Saito (ks91), 2025.

A version of Main.py that takes input from REST API instead of
GUI events. It is assumed that the robot has been set up using
the original Main.py client software.
"""

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
        self.distance = '0cm'
        self.pinch = False
        self.drop = False


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
                if cmdArray[-1] != '':
                    restCmd = cmdArray[-1]
                    cmdArray = cmdArray[:-1]
            for oneCmd in cmdArray:
                message = oneCmd.split('#')
                if cmd.CMD_SONIC in message:
                    self.distance = f'{message[1]}cm'
                elif cmd.CMD_ACTION in message:
                    if message[1] == '10':
                        self.pinch = False
                    elif message[1] == '20':
                        self.drop = False


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


# Endpoint to adjust speed (2 <= speed <= 10; 8 by default)
@app.route('/speed', methods=['POST'])
@app.route('/speed/<string:value>', methods=['POST'])
def adjust_speed(value=None):
    if value is None:
        value = DEFAULT_MOVE_SPEED
    g.service.move_speed = value
    return jsonify({'status': 'Speed set', 'speed': int(value)}), 200


# Endpoint to get the speed
@app.route('/speed', methods=['GET'])
def get_speed():
    return jsonify({'speed': int(g.service.move_speed)}), 200


# End point to move or stop
@app.route('/stop', methods=['POST'])
@app.route('/motor', methods=['POST'])
@app.route('/motor/<string:left>/<string:right>', methods=['POST'])
def motor(left=None, right=None):
    if left is None:
        left = '0'
        right = '0'
    left_speed = int(left) * int(g.service.move_speed) * 20
    right_speed = int(right) * int(g.service.move_speed) * 20
    command = cmd.CMD_MOTOR + f'#{left_speed}#{right_speed}\n'
    g.service.client.sendData(command)
    return jsonify({
        'status': 'Moving',
        'left': int(left),
        'right': int(right)
    }), 200


# Endpoint to control the arm
@app.route('/arm', methods=['POST'])
@app.route('/arm/<string:angle>', methods=['POST'])
def arm(angle=None):
    if angle is None:
        angle = '150'
    command = cmd.CMD_SERVO + f'#1#{angle}\n'
    g.service.client.sendData(command)
    return jsonify({'status': 'Arm angle changed', 'angle': angle}), 200


# Endpoint to control the grapple
@app.route('/grapple', methods=['POST'])
@app.route('/grapple/<string:angle>', methods=['POST'])
def grapple(angle=None):
    if angle is None:
        angle = '0'
    command = cmd.CMD_SERVO + f'#0#{angle}\n'
    g.service.client.sendData(command)
    return jsonify({'status': 'Grapple angle changed', 'angle': angle}), 200


# Endpoint for sonic
@app.route('/sonic', methods=['GET'])
def sonic():
    command = cmd.CMD_SONIC + '\n'
    g.service.client.sendData(command)
    time.sleep(0.1)
    distance = g.service.distance
    return jsonify({'status': 'Sonic data requested', 'distance': distance}), 200


# Endpoint to set LED mode (0 : off, 1 to 5)
@app.route('/led/mode', methods=['POST'])
@app.route('/led/mode/<string:value>', methods=['POST'])
def set_led_mode(value=None):
    if value is None:
        value = '0'
    command = cmd.CMD_LED_MOD + f'#{value}\n'
    g.service.client.sendData(command)
    return jsonify({'status': 'LED mode set', 'mode': int(value)}), 200


# Endpoint to set LED color
@app.route('/led/color', methods=['POST'])
@app.route('/led/color/<string:red>/<string:green>/<string:blue>', methods=['POST'])
def set_led_color(red=None, green=None, blue=None):
    if red is None:
        red = '255'
        green = '255'
        blue = '255'
    command = cmd.CMD_LED + f'#255#{red}#{green}#{blue}\n'
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
