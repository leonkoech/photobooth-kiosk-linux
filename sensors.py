from flask import Flask, render_template_string
import OPi.GPIO as GPIO
import threading
import time

app = Flask(__name__)


# Setup the GPIO pins
MQ3_PIN = 11 
drunk_value = 0

#GPIO.setboard(GPIO.PCPCPLUS) 
GPIO.setboard(GPIO.H616)   # Orange Pi PC board
GPIO.setmode(GPIO.BOARD)  


# Set MQ3 pin should make sure it's analog
GPIO.setup(MQ3_PIN, GPIO.IN)

# Define thresholds for Sober and Drunk
SOBER_THRESHOLD = 120  # Adjust as needed
DRUNK_THRESHOLD = 400  # Adjust as needed

sensor_value = None
status = None
countdown = 2
time_left = None


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


def read_mq3_sensor_continuously():
    countdown_timer()
    global sensor_value, status
    while True:
        sensor_value = read_mq3_sensor()
        status = get_status(sensor_value)
        time.sleep(1)  # Adjust the sleep time as needed

def countdown_timer():
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
    return sensor_value

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
        {% if time_left > 0 || time_left == None%}
          <h1>To Start, you'd have to wait for 2 minutes, at first</h1>
          <p> {{time_left}} </p>
          {% else %}
          <h1 class="mt-5">Sensor Values</h1>
          {% if sensor_value is not none %}
          <p class="lead">MQ-3 Sensor Value: {{ sensor_value }}</p>
          <p class="lead">Status: {{ status }}</p>
          {% else %}
          <p class="lead">Move closer to see MQ-3 sensor values.</p>
          {% endif %}
        {% endif %}

        </div>
      </body>
    </html>
    '''
    return render_template_string(html, sensor_value=sensor_value, status=status)

if __name__ == '__main__':
    try:
        threading.Thread(target=read_mq3_sensor_continuously, daemon=True).start()
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
