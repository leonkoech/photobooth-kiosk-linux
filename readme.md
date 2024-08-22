
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
Part 18 of this tutorial helps in testing UART and activating it 
[https://orangepi.net/wp-content/uploads/2023/12/OrangePi_Zero3_H618_user-manual_v1.1.pdf](https://orangepi.net/wp-content/uploads/2023/12/OrangePi_Zero3_H618_user-manual_v1.1.pdf)
