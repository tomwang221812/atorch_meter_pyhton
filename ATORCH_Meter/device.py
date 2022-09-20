from asyncio.log import logger
import os
import asyncio

from .logger import AverageMeter, csv_logger
from datetime import datetime

import bleak
from bleak import BleakScanner, BleakClient

print('(**) Bleak library version {}'.format(bleak.__version__))

class TOOLS:
    def __init__(self, verbose=False):
        
        self.verbose = verbose 
        self.raw_data_buffer = None

    def detection_callback(self, device, advertisement_data):
        
        address, name, rssi = device.address, device.name, device.rssi
        uuids, m_data = device.metadata['uuids'], device.metadata['manufacturer_data']

        if self.verbose:
            print('\nAddress:', address, 'Name:', name, "RSSI:", rssi)

            if m_data:
                print('\t - Manufacturer:')
                
                for (_mkey, _mvalue) in m_data.items():
                    print('\t\t{}: {}'.format(_mkey, _mvalue))
            
            if uuids:
                for _uuid_idx, _uuid in enumerate(uuids):
                    print('\t - UUID {:d}: '.format(_uuid_idx), _uuid)           

    async def discover_devices(self, wait_time=5.0):
        scanner = BleakScanner(self.detection_callback)
        await scanner.start()
        await asyncio.sleep(wait_time)
        await scanner.stop()

        return scanner.discovered_devices

    def lsble(self):
        asyncio.run(self.discover_devices())

class ATORCH_USB_METER():

    def __init__(self, model='UD24', device_name=None, device_address=None, log_dir=None):
        self.model = model
        self.log_dir = log_dir

        self.ble_device_name = None
        self.ble_device_address = None

        self.ble_send_uuid = None
        self.ble_receive_uuid = None
        self.char_notify_uuid = None

        self.disconnected_event = asyncio.Event()
        self.notifiing = False
        self.device = None
        self.client = None
        self.services = None

        self.verbose = True
        
        self.raw_data_buffer = None

        start_datetime_now = datetime.now()
        self.start_datetime = start_datetime_now.strftime("%Y%m%d_%H%M%S")
        print("(**) Start now:", self.start_datetime)

        self.avgmeter = {'v': AverageMeter(), 'i': AverageMeter(), 'w': AverageMeter(), 'r': AverageMeter()}
        self.csv_logger = None
        self.csv_writter = None
        self.csv_header = ['Time', 'Voltage (V)', 'Current (A)', 'Power (W)', 'Resistance (Ohm)', 'DATA+', 'DATA-', 'Capacity (mAh)', 'Electricity (wAh)', 'Temperature (C)']

    async def find_device(self, timeout=60., device_name=None, device_address=None):

        assert device_name or device_address, f'(EE) None of device named {self.ble_device_name} or address {self.ble_device_address} found! Not given?'

        if device_address: self.ble_device_address = device_address
        if device_name: self.ble_device_name = device_name
        
        if self.ble_device_address:
            print(f'(**) Start to find the device by address {self.ble_device_address}')
            self.device = await BleakScanner.find_device_by_address(self.ble_device_address, timeout=timeout)
            self.ble_device_name = self.device.name
        
        if self.ble_device_name:
            print(f'(**) Start to find the device by name {self.ble_device_name}')
            self.device = await BleakScanner.find_device_by_filter(lambda d, ad: d.name and d.name.lower() == self.ble_device_name.lower(), timeout=timeout)
            self.ble_device_address = self.device.address

    async def disconnected_callback(self, client):
        print("Disconnected callback called!")
        self.disconnected_event.set()
        
    async def connect_ble(self, timeout=60., device_name=None, device_address=None):

        await self.find_device(timeout, device_name, device_address)        

        assert self.device, f'(EE) None of device named {self.ble_device_name} or address {self.ble_device_address} found! Not given?'
        assert self.device.metadata, f'(EE) No meta data found from device {self.ble_device_name} ({self.ble_device_address})'
        assert len(self.device.metadata) == 2, f'(EE) The length of UUIDs must be 2'

        self.ble_receive_uuid = self.device.metadata['uuids'][0]
        self.ble_send_uuid = self.device.metadata['uuids'][1]

        print(f'(**) Success to find the device {self.ble_device_name}: {self.ble_device_address}')
        print(f'(**) With receive UUID: {self.ble_receive_uuid}')
        print(f'(**) With send UUID: {self.ble_send_uuid}')

        if self.log_dir:
            csv_fname = '{:s}_{:s}_{:s}'.format(self.ble_device_name, self.ble_device_address.replace(':', ''), self.start_datetime)
            self.csv_logger = csv_logger(os.path.join(self.log_dir ,'{}.csv'.format(csv_fname)), self.csv_header)

        while True:
            self.client = BleakClient(self.ble_device_address, timeout=3600)
            try:
                print('(**) Try to connect to address {}'.format(self.ble_device_address))
                await self.client.connect()

                if self.client.is_connected:
                    print(f'(!!) Connected device {self.ble_device_name} with address {self.ble_device_address} as client!')
                
                    self.services = await self.client.get_services()
                    for sidx, service in enumerate(self.client.services):
                        for cidx, char in enumerate(service.characteristics):
                            if 'notify' in char.properties:
                                print(f'(!!) Found notify characteristic {char} in service {service}')
                                self.char_notify_uuid = char.uuid
                
                    await self.notify_starter(self.client, self.char_notify_uuid)
                else:
                    print('(EE) Client cannot be connected!')
                    await asyncio.sleep(1)                  
            except asyncio.CancelledError:
                await asyncio.sleep(1)
                print('(EE) Current task has been canceled!')
            except Exception as e:
                print(e)
            finally:
                await self.client.disconnect()
                await asyncio.sleep(1)
                print('(!!) Disconnected!')

    async def reconnect_client(self, client):
        await client.connect()

    async def notify_starter(self, client = None, char_uuid = None, check_interval=1):

        assert client
        assert char_uuid

        try:
            if client.is_connected:
                await client.start_notify(char_uuid, self.notification_handler)
                while (client.is_connected):
                    await asyncio.sleep(check_interval)
        except Exception as e:
            print('(EE) Start notify error!', e)
        finally:
            if self.client.is_connected:
                print('(!!) Stop notify... Char UUID: {}'.format(char_uuid))
                await client.stop_notify(char_uuid)
            else:
                print('(!!) Device disconnected during receiving notifications')
                
        

    def decode_usb_data(self, data: bytearray, magic_header: str='ff55', data_type: str='01', device_type: str='03') -> dict:
        if len(data) == 20 and self.bytearray2str(data, 0, 2) == magic_header and self.bytearray2str(data, 2, 1) == data_type and self.bytearray2str(data, 3, 1) == device_type:
            self.raw_data_buffer = data
        elif len(data) == 16 and self.raw_data_buffer:
            self.raw_data_buffer += data
            v = self.byte2num(self.raw_data_buffer, 4, 3, 100.)
            i = self.byte2num(self.raw_data_buffer, 7, 3, 100.)
            w = self.get_power(v, i)
            r = self.get_resistance(v, i)
            self.avgmeter['v'].update(v)
            self.avgmeter['i'].update(i)
            self.avgmeter['w'].update(w)
            self.avgmeter['r'].update(r)
            results = {
                'time': '{:03d}:{:02d}:{:02d}'.format(int(self.byte2num(self.raw_data_buffer, 23, 2)),
                                                      int(self.byte2num(self.raw_data_buffer, 25, 1)),
                                                      int(self.byte2num(self.raw_data_buffer, 26, 1)),
                                                     ),
                'voltage': v,
                'current': i,
                'power': w,
                'resistance': r,
                'usb_data_positive': self.byte2num(self.raw_data_buffer, 19, 2, 100.),
                'usb_data_negative': self.byte2num(self.raw_data_buffer, 17, 2, 100.),
                'capacity': int(self.byte2num(self.raw_data_buffer, 10, 3)),
                'electricity': self.byte2num(self.raw_data_buffer, 13, 4, 100.),
                'temperature': self.byte2num(self.raw_data_buffer, 21, 3),
                }
            return results
        else:
            print('(EE) Data length not not 20 or 16 or magic header not matched, skipping...')

    def get_power(self, v, i):
        return round(v * i, 2)

    def get_resistance(self, v, i):
        if i <= 0.01: i = 1e-12
        return round(v / i, 2)

    def bytearray2str(self, raw_data: bytearray, start_byte: int, byte_length: int=1):
        return ''.join('{:02x}'.format(x) for x in raw_data)[2*start_byte: 2*start_byte + 2*byte_length]

    def byte2num(self, raw_data: bytearray, start_byte: int, byte_length: int, scale: float=1.) -> float:
        return int.from_bytes(raw_data[start_byte: start_byte + byte_length], 'big', signed=False) / scale

    def notification_handler(self, sender, data: bytearray):
        decoded = self.decode_usb_data(data)
        if decoded: 
            if self.csv_logger:
                self.csv_logger.writerow(decoded.values())
            self.print_to_console(decoded)

    def print_to_console(self, usb_data):
        print('\nTime:', usb_data['time'])
        print('\tVotage : {:>2.2f}V\tAvg:{:>2.2f}V\tMin:{:>2.2f}V\tMax:{:2.2f}V'.format(usb_data["voltage"], self.avgmeter['v'].avg, self.avgmeter['v'].min, self.avgmeter['v'].max))
        print('\tCurrent: {:>2.2f}A\tAvg:{:>2.2f}A\tMin:{:>2.2f}A\tMax:{:2.2f}A'.format(usb_data["current"], self.avgmeter['i'].avg, self.avgmeter['i'].min, self.avgmeter['i'].max))
        print('\tPower  : {:>2.2f}W\tAvg:{:>2.2f}W\tMin:{:>2.2f}W\tMax:{:2.2f}W'.format(usb_data["power"], self.avgmeter['w'].avg, self.avgmeter['w'].min, self.avgmeter['w'].max))
        print('\tUSB D+ : {:>2.2f}\tUSB D-: {:2.2f}'.format(usb_data["usb_data_positive"], usb_data["usb_data_negative"]))
        print('\tCapacity: {:04d}mAh \tEletricity: {:>6.2f}Wh'.format(usb_data["capacity"], usb_data["electricity"]))

    def connect(self):

        if self.ble_device_address:
            print('(**) Start to connect using device address {}'.format(self.ble_device_address))
            asyncio.run(self.connect_ble(device_address = self.ble_device_address))
        if self.ble_device_name:
            print('(**) Start to connect using device name {}'.format(self.ble_device_address))
            asyncio.run(self.connect_ble(device_name = self.ble_device_name))
        print('(WW) Device address or device name not given...')
        
        print('(**) Serching for device model {:s}'.format(self.model))

        if self.model.lower() == 'ud18' or self.model.lower() == 'j7-c':
            asyncio.run(self.connect_ble(device_name = 'UD18-BLE'))
        elif self.model.lower() == 'ud24':
            asyncio.run(self.connect_ble(device_name = 'UD24-BLE'))
        else:
            print('(EE) Device not supported')
        