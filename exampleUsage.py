#!/usr/bin/env python

from ps4262 import ps4262
import pylab as plt
import time
import sys
import numpy as np

voltageRange = 5 # volts
requestedSamplingInterval = 1e-6 # seconds
captureDuration = 0.3 # seconds
triggersPerMinute = 30

ps = ps4262(VRange = voltageRange, requestedSamplingInterval = requestedSamplingInterval, tCapture = captureDuration, triggersPerMinute = triggersPerMinute)

print("Metadata:")
print (ps.getMetadata())
print("")

def plot(x,y):
    plt.ion()
    plt.figure()
    plt.plot(x, y)
    plt.grid(True)
    plt.title("Picoscope 4000 waveform")
    plt.ylabel("Counts")
    plt.xlabel("Time [s]")
    #plt.legend()
    plt.show()
    plt.pause(.001)

i = 0
while i < 5:
    i = i + 1
    print("Waiting for data...")
    #data = ps.getData() # this call will block until data is ready
    while len(ps.data) == 0:
        pass
    print("Data ready!")
    data = ps.data.pop()
    y = data["raw_data"]
    x = np.linspace(data["t0"],data['t_end'],len(y))
    print("Drawing plot from trigger number", data["nTriggers"])
    # plot the data
    plot(x,y)
    print("")

print("Trigger frequency is", ps.triggerFrequency, "[Hz]")
time.sleep(2)

# change sampling interval/capture duration on the fly
captureDuration = 0.01 # seconds
ps.setTimeBase(requestedSamplingInterval = requestedSamplingInterval, tCapture = captureDuration)

ps.setFGen(triggersPerMinute = 240)
print("Trigger frequency set to", ps.triggerFrequency, "[Hz]")
time.sleep(5)

sleepTime  = 5
t = 0
t0 = time.time()
ps.data.clear() # throw away any triggers we just missed while sleeping
# now gather new triggers for 5 seconds...
while t < sleepTime:
    print("Waiting for edge...")

    #data = ps.getData() # this call will block until data is ready
    while len(ps.data) == 0:
        pass
    print("Trigger seen!")
    data = ps.data.pop()
    print (data)
    print("")
    t = time.time() - t0

print("We've seen", ps.edgesCaught, "triggers since the beginning of time.")
print("Disabling trigger train, then waiting 3 seconds")
ps.setFGen(triggersPerMinute=0)  # disable trigger train
time.sleep(3)
print("We've seen", ps.edgesCaught, "triggers since the beginning of time.")

# clear the data queue
ps.data.clear()

print("Sending three single shot triggers...")
# now fire three single shots:
ps.setFGen(triggersPerMinute=-1)
time.sleep(0.05) # can't ask for single shot triggers too fast!
ps.setFGen(triggersPerMinute=-1)
time.sleep(0.05)
ps.setFGen(triggersPerMinute=-1)

# wait until we've got those three triggers
while len(ps.data) < 3:
    pass

print("We've seen", ps.edgesCaught, "triggers since the beginning of time.")

time.sleep(10) # give the user a chance to look at the plots

# reset the global trigger count to 0
ps.resetTriggerCount()

