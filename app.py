from flask import Flask, render_template_string
import OPi.GPIO as GPIO
import time

app = Flask(__name__)

# Setup the GPIO pins
MQ3_PIN = 73  # PC9 mapped to GPIO73
TRIG_PIN = 72  # PC8 mapped to GPIO72
ECHO_PIN = 71  # PC7 mapped to GPIO71

GPIO.setmode(GPIO.BCM)  # Using BCM numbering which matches the GPIO numbers
GPIO.setup(MQ3_PIN, GPIO.IN)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)

# Define thresholds for Sober and Drunk
SOBER_THRESHOLD = 120  # Adjust as needed
DRUNK_THRESHOLD = 400  # Adjust as needed

# Function to read MQ-3 sensor
def read_mq3_sensor():
    value = GPIO.input(MQ3_PIN)
    return value

# Function to get status from MQ-3 sensor value
def get_status(sensor_value):
    if sensor_value < SOBER_THRESHOLD:
        return "Stone Cold Sober"
    elif SOBER_THRESHOLD <= sensor_value < DRUNK_THRESHOLD:
        return "Drinking but within legal limits"
    else:
        return "DRUNK"

# Function to measure distance using ultrasonic sensor
def measure_distance():
    GPIO.output(TRIG_PIN, True)
    time.sleep(0.00001)
    GPIO.output(TRIG_PIN, False)

    start_time = time.time()
    stop_time = time.time()

    while GPIO.input(ECHO_PIN) == 0:
        start_time = time.time()
    
    while GPIO.input(ECHO_PIN) == 1:
        stop_time = time.time()

    elapsed_time = stop_time - start_time
    distance = (elapsed_time * 34300) / 2
    return distance

@app.route('/')
def index():
    distance = measure_distance()
    sensor_value = None
    status = None
    if distance <= 10:
        sensor_value = read_mq3_sensor()
        status = get_status(sensor_value)
    
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
          <h1 class="mt-5">Sensor Values</h1>
          <p class="lead">Current distance: {{ distance }} cm</p>
          {% if sensor_value is not none %}
          <p class="lead">MQ-3 Sensor Value: {{ sensor_value }}</p>
          <p class="lead">Status: {{ status }}</p>
          {% else %}
          <p class="lead">Move closer to see MQ-3 sensor values.</p>
          {% endif %}
        </div>
      </body>
    </html>
    '''
    return render_template_string(html, distance=distance, sensor_value=sensor_value, status=status)

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
