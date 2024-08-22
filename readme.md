
open a terminal 
run "git pull origin main" 
then run a virtual env > activate it > run "pip3 install -r requirements.txt"

```
sudo apt-get update
sudo apt-get install python3-dev git
git clone https://github.com/eutim/OPI.GPIO
cd OPI.GPIO
sudo python3 setup.py install
```

pin connection is based on GPIO of H616


## Activating UART

Since I am using an ESP32  for analog data of the MQ3 (probably overkill) but I lack a ADC to i2C converter at the moment. When I get it I will replace it 
the orange pi needs to have UART enabled. We do this by changing the contents of boot/orangepiEnv.txt to have the overlays like below. 
Note: Don't edit your current overlay_prefix

overlay_prefix=sun8i-h3
overlays=usbhost2 usbhost3 uart1 uart2
