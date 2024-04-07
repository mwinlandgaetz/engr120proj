import machine
import utime

#Pin assignment
switchPin = machine.Pin(1,machine.Pin.IN)
switchAdcPin = machine.Pin(2,machine.Pin.IN)
adc = machine.ADC(26)
adcstatus = switchAdcPin.value()
pinstatus = switchPin.value()
i = 0
pindex = [machine.Pin(j,machine.Pin.OUT) for j in range(6,16)]

while True:
    if(pinstatus == 1 and switchPin.value() == 0):
        pindex[i].off()
        i+=1
        if(i>=len(pindex)):
            i=0
        pindex[i].on()
        print("Changing to %d." % (i+6))
    if(adcstatus == 0 and switchAdcPin.value() == 1):
        print(adc.read_u16())
    pinstatus = switchPin.value()
    adcstatus = switchAdcPin.value()
    utime.sleep(0.1)