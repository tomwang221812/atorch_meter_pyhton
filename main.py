from ATORCH_Meter import device

if __name__ == '__main__':
    
    meter = device.ATORCH_USB_METER(log_dir='./')
    meter.connect()