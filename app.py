from flask import Flask, render_template_string
import OPi.GPIO as GPIO

app = Flask(__name__)

# Setup the GPIO pin for MQ-3 sensor
MQ3_PIN = 7  # Adjust this pin number according to your setup
GPIO.setmode(GPIO.BOARD)
GPIO.setup(MQ3_PIN, GPIO.IN)

# Define thresholds for Sober and Drunk
SOBER_THRESHOLD = 120
DRUNK_THRESHOLD = 400

def read_mq3_sensor():
    # Placeholder for actual analog read logic if needed
    # For now, read digital signal from the pin (High or Low)
    value = GPIO.input(MQ3_PIN)
    return value

def get_status(sensor_value):
    """Determine the status based on the sensor value"""
    if sensor_value < SOBER_THRESHOLD:
        return "Stone Cold Sober"
    elif SOBER_THRESHOLD <= sensor_value < DRUNK_THRESHOLD:
        return "Drinking but within legal limits"
    else:
        return "DRUNK"

@app.route('/')
def index():
    sensor_value = read_mq3_sensor()
    status = get_status(sensor_value)
    html = '''
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>MQ-3 Sensor Value</title>
      </head>
      <body>
        <div class="container">
          <h1 class="mt-5">MQ-3 Sensor Value</h1>
          <p class="lead">Current value from the sensor: {{ sensor_value }}</p>
          <p class="lead">Status: {{ status }}</p>
        </div>
      </body>
    </html>
    '''
    return render_template_string(html, sensor_value=sensor_value, status=status)

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
