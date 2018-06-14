# written by grey@christoforo.net
# on 21 Feb 2018

from picoscope import ps4000
import numpy as np
import threading
import pickle
import time
import concurrent.futures
from collections import deque

class ps4262:
    """
    picotech PS4262 library
    """
    currentScaleFactor = 1/10000000 # amps per volt through our LPM7721 eval board
    persistentFile = '/var/tmp/edgeCount.bin'
    pretrig = 0.1  # 10% of the output data will be from before the trigger event

    # for AWG
    nWaveformSamples = 2 ** 12
    waveform = np.zeros(nWaveformSamples)
    def __init__(self, VRange = 5, requestedSamplingInterval = 1e-6, tCapture = 0.3, triggersPerMinute = 30):
        """
        picotech PS4262 library constructor
        """
        # this opens the device
        self.ps = ps4000.PS4000(blockReadyCB = self.blockReady)
        self.lastTriggerTime = None # stores time of last trigger edge
        self.data = deque()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers = 1)

        # setup sampling interval
        self.setTimeBase(requestedSamplingInterval = requestedSamplingInterval, tCapture = tCapture)

        # setup current collection channel (A)
        self._setChannel(VRange = VRange)

        # turn on the function generator
        self.setFGen(triggersPerMinute = triggersPerMinute)

        # setup triggering
        self.executor.submit(self.ps.setExtTriggerRange, VRange = 0.5)
        # 0 ms timeout means wait forever for the next trigger
        self.executor.submit(self.ps.setSimpleTrigger, 'EXT', 0.15, 'Rising', delay=0, timeout_ms = 0, enabled=True)
        
        try:
            self.fp = open(self.persistentFile, mode='r+b')
            self.edgesCaught = pickle.load(self.fp)
            self.fp.seek(0)
        except:
            self.edgesCaught = 0
            self.fp = open(self.persistentFile, mode='wb')
            pickle.dump(self.edgesCaught,self.fp,-1)
            self.fp.flush()
            self.fp.seek(0)
            
        self.doFetch = True  # when new scope data comes in, fetch it
        self._run(None)

    def __del__(self):
        try:
            self.executor.submit(self.ps.stop)
        except:
            pass

        try:
            self.ps.close()
        except:
            pass

        try:
            self.fp.close()
        except:
            pass

        try:
            self.executor.shutdown()
        except:
            pass

    def resetTriggerCount(self):
        self.edgesCaught = 0
        pickle.dump(self.edgesCaught,self.fp,-1)
        self.fp.flush()
        self.fp.seek(0)
    
    # this can't be called externally (it doesn't go into the executor queue)
    def _fetchData(self):
        if self.doFetch:
            (raw_data, numSamplesReturned, overflow) = self.ps.getDataRaw('A', self.nSamples)
            dtype = np.float64
            channel = self.ps.CHANNELS['A']
            voltage_scale = self.ps.CHRange[channel] / dtype(self.ps.getMaxValue())
            voltage_offset = self.ps.CHOffset[channel]

            #voltageData = self.ps.getDataV('A', self.nSamples, returnOverflow=False)
            self.data.append ({"voltage_offset":voltage_offset, "voltage_scale":voltage_scale, "current_scale":self.currentScaleFactor, "nTriggers": self.edgesCaught, "t0": self.timeVector[0], "t_end": self.timeVector[-1], "raw_data": raw_data, "timestamp": self.lastTriggerTime, "yLabel": "Counts", "xLabel": "Time", "yUnits": "counts", "xUnits": "s"})
            # then to recover the proper data into dataI, one should do:
            # dataI = np.empty(raw_data.size, dtype=type(voltage_scale))
            #np.multiply(raw_data, voltage_scale, dataI)
            #np.subtract(dataI, voltage_offset, dataI)
            #np.multiply(dataI, current_scale, dataI)

    def blockReady(self,handle,error,void):
        self.lastTriggerTime = time.time() # returns seconds since 1970 GMT
        self.edgesCaught = self.edgesCaught +  1  # incriment edge count
        pickle.dump(self.edgesCaught,self.fp,-1)
        self.fp.flush()
        self.fp.seek(0)
        
        future = self.executor.submit(self._fetchData)
        future.add_done_callback(self._run)

    def setFGen(self, triggersPerMinute = 10):
        """Sets picoscope function generator parameters
        use triggersPerMinute = 0 to disable the function generator
        use triggersPerMinute = -1 to immediately fire off one trigger pulse

        Single shot trigger mode might not catch your request
        if you ask for it within 50ms of the last time you asked.
        """
        frequency = triggersPerMinute / 60
        self.triggerFrequency = frequency
        
        if frequency > 0:  # run continuously mode
            duration = 1/frequency
            self.singleShotMode = False
            
            # for short, 5ms pulses using the arbitrary waveform generator
            sPerSample = duration/len(self.waveform)
            samplesPer5ms = int(np.floor(5e-3/sPerSample))
            self.waveform[0:samplesPer5ms] = 1
            self.doFetch = False  # must disable data collection now
            future = self.executor.submit(self.ps.setAWGSimple, self.waveform, duration, offsetVoltage=0.0, indexMode="Single", triggerSource='None', pkToPk=2.0, shots=0, triggerType="Rising")
            concurrent.futures.wait([future])
            self.doFetch = True
            
            # for 50% duty cycle square wave
            #self.executor.submit(self.ps.setSigGenBuiltInSimple, offsetVoltage=offsetVoltage, pkToPk=pkToPk, waveType=waveType, frequency=frequency, shots=shots, stopFreq=stopFreq)
            
        elif frequency == 0:  # disable signal generator
            duration = 0.1
            self.singleShotMode = False
            self.waveform[:] = 0
            self.doFetch = False
            future = self.executor.submit(self.ps.setAWGSimple, self.waveform, duration, offsetVoltage=0.0, indexMode="Single", triggerSource='SoftTrig', pkToPk=2.0, shots=1, triggerType="Rising")
            concurrent.futures.wait([future])
            self.doFetch = True
            
            future = self.executor.submit(self.ps._lowLevelSigGenSoftwareControl,0)

        else:  # negative frequencies mean single shot mode
            if not self.singleShotMode:
                duration = 0.005
                self.waveform[:] = 1
                self.waveform[-10:] = 0 # last 10 slots are zero volts so that voltage doesn't stay high
                self.doFetch = False
                future = self.executor.submit(self.ps.setAWGSimple, self.waveform, duration, offsetVoltage=0.0, indexMode="Single", triggerSource="SoftTrig", pkToPk=2.0, shots=1, triggerType="Rising")
                concurrent.futures.wait([future])
                self.doFetch = True
                self.singleShotMode = True
            future = self.executor.submit(self.ps._lowLevelSigGenSoftwareControl,0)

    def _setChannel(self, VRange = 2):
        self.VRange = VRange
        future = self.executor.submit(self.ps.setChannel, channel='A', coupling='DC', VRange=VRange, VOffset=0.0, enabled=True, BWLimited=0, probeAttenuation=1.0)

    def setTimeBase(self, requestedSamplingInterval=1e-6, tCapture = 0.3):
        """
        Sets sampling interval and capture duration, given in seconds
        Capture duration is measured from after the trigger event
        The voltage data returned will actually be tCapture * 1.1 duration long because
        10% of the data is from before the capture event
        """
        self.requestedSamplingInterval = requestedSamplingInterval
        self.tCapture = tCapture

        future = self.executor.submit(self.ps.setSamplingInterval, sampleInterval =
                                          requestedSamplingInterval, duration = tCapture*1.1, oversample=0,
                                                                       segmentIndex=0)
        (self.actualSamplingInterval, self.nSamples, maxSamples) = future.result()

    def getMetadata(self):
        """
        Returns metadata struct
        """
        metadata = {"Voltage Range" : self.VRange,
        "Trigger Frequency": self.triggerFrequency,
        "Actual Sampling Interval": self.actualSamplingInterval,
        "Samples Per Waveform": self.nSamples,
        "Requested Sampling Interval": self.requestedSamplingInterval,
        "Capture Time": self.tCapture}
        return metadata

    def _run(self,future):
        """
        This arms the trigger
        """
        future = self.executor.submit(self.ps.runBlock, pretrig = self.pretrig, segmentIndex = 0)
        self.timeVector = (np.arange(self.ps.noSamples) - int(round(self.ps.noSamples * self.pretrig))) * self.actualSamplingInterval