from flask import Flask, render_template_string
import OPi.GPIO as GPIO
import time

app = Flask(__name__)

# Setup the GPIO pin for MQ-3 sensor
MQ3_PIN = 7  # Adjust this pin number according to your setup
GPIO.setmode(GPIO.BOARD)
GPIO.setup(MQ3_PIN, GPIO.IN)

def read_mq3_sensor():
    # Read the sensor data; this is a placeholder function. You may need to calibrate and adjust it
    # as per the MQ-3 sensor's datasheet and your specific requirements.
    # For now, it simply reads the digital value (high or low) from the pin.
    value = GPIO.input(MQ3_PIN)
    return value

@app.route('/')
def index():
    sensor_value = read_mq3_sensor()
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
        </div>
      </body>
    </html>
    '''
    return render_template_string(html, sensor_value=sensor_value)

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
