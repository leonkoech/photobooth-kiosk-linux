from flask import Flask, render_template_string
import OPi.GPIO as GPIO
import threading
import time

app = Flask(__name__)

# Setup the GPIO pins
MQ3_PIN = 11 
TRIGGER_SENSOR = 13
ECHO_SENSOR = 15

drunk_value = 0

GPIO.setboard(GPIO.H616)   # Orange Pi PC board
GPIO.setmode(GPIO.BOARD)  

# Set MQ3 pin should make sure it's analog (Assuming MQ3 sensor has a digital output pin)
GPIO.setup(MQ3_PIN, GPIO.IN)
GPIO.setup(TRIGGER_SENSOR, GPIO.OUT)
GPIO.setup(ECHO_SENSOR, GPIO.IN)

# Define thresholds for Sober and Drunk
SOBER_THRESHOLD = 120  # Adjust as needed
DRUNK_THRESHOLD = 400  # Adjust as needed
SOUND_SPEED = 0.034
CM_TO_INCH = 0.393701

sensor_value = None
status = None
countdown = 2
time_left = None
duration = None
distanceCm = None
distanceInch = None

# Function to read MQ-3 sensor
def read_mq3_sensor():
    value = GPIO.input(MQ3_PIN)  # This is only valid if MQ-3 is connected to a digital pin
    return value

# Function to calculate distance using the ultrasonic sensor
def get_distance_sensor():
    global duration, distanceCm, distanceInch
    while True:
        GPIO.output(TRIGGER_SENSOR, GPIO.LOW)
        time.sleep(0.02)
        GPIO.output(TRIGGER_SENSOR, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(TRIGGER_SENSOR, GPIO.LOW)
        
        # Wait for the echo to start
        while GPIO.input(ECHO_SENSOR) == 0:
            start_time = time.time()
        
        # Wait for the echo to stop
        while GPIO.input(ECHO_SENSOR) == 1:
            stop_time = time.time()
        
        duration = stop_time - start_time
        distanceCm = (duration * SOUND_SPEED) / 2
        distanceInch = distanceCm * CM_TO_INCH
        time.sleep(1)  # Add a delay to avoid continuous triggering

# Function to get status from MQ-3 sensor value
def get_status(sensor_value):
    if sensor_value < SOBER_THRESHOLD:
        return "Stone Cold Sober"
    elif SOBER_THRESHOLD <= sensor_value < DRUNK_THRESHOLD:
        return "Drinking but within legal limits"
    else:
        return "DRUNK"

# Function to read the MQ-3 sensor continuously
def read_mq3_sensor_continuously():
    countdown_timer()
    global sensor_value, status
    while True:
        sensor_value = read_mq3_sensor()
        status = get_status(sensor_value)
        time.sleep(1)  # Adjust the sleep time as needed

# Countdown timer function
def countdown_timer():
    global time_left
    total_seconds = countdown * 60
    while total_seconds:
        minutes, seconds = divmod(total_seconds, 60)
        print(f'{minutes:02d}:{seconds:02d}', end='\r')
        time.sleep(1)
        total_seconds -= 1
        time_left = total_seconds
    time_left = 0

@app.route('/sensor_value')
def alcohol_level():
    return str(sensor_value)

@app.route('/')
def index():
    html = '''
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>Sensor Values</title>
      </head>
      <body>
        <div class="container">
        {% if time_left is None or time_left > 0 %}
          <h1>To Start, you'd have to wait for 2 minutes, at first</h1>
          <p>Time left: {{ time_left }}</p>
        {% else %}
          <h1 class="mt-5">Sensor Values</h1>
          {% if sensor_value is not None %}
          <p class="lead">MQ-3 Sensor Value: {{ sensor_value }}</p>
          <p class="lead">Status: {{ status }}</p>
          <p>Distance: {{ distanceCm }} cm ({{ distanceInch }} inches)</p>
          {% else %}
          <p class="lead">Move closer to see MQ-3 sensor values.</p>
          {% endif %}
        {% endif %}
        </div>
      </body>
    </html>
    '''
    return render_template_string(html, sensor_value=sensor_value, status=status, distanceCm=distanceCm, distanceInch=distanceInch, time_left=time_left)

if __name__ == '__main__':
    try:
        threading.Thread(target=read_mq3_sensor_continuously, daemon=True).start()
        threading.Thread(target=get_distance_sensor, daemon=True).start()
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
