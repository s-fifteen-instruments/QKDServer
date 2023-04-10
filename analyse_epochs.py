from struct import unpack
from datetime import datetime
import os
from pathlib import Path
from typing import NamedTuple
import numpy as np

os.chdir('/epoch_files')
ls = os.listdir()
ls.remove('notify.pipe')
save_file = 'epoch_analy.npy'
try:
    ls.remove(save_file)
except ValueError:
    print('No saved file yet')

class HeadT7(NamedTuple):
    tag: int
    epoch: int
    num_epoch: int
    length_bits: int

def read_T7_header(filename: str):
   if Path(filename).is_file():
      with open(filename, 'rb') as f:
         head_info = f.read(16)
   headt7 = HeadT7._make(unpack('iIIi', head_info))
   if (headt7.tag != 0x107 and headt7.tag != 7):
      print(f'{filename} is not a Type7 file')
   return headt7

def get_time(epoch: int):
   tz_offset = 8*60*60
   return (epoch<<29)/1000000000 + tz_offset

date_int = []
date = []
num_epoch = []
bits = []
ingested_bits = []
data = []

for i in ls:
   h = read_T7_header(i)
   date_int.append(get_time(h.epoch))
   date.append(datetime.fromtimestamp(get_time(h.epoch)))
   num_epoch.append(h.num_epoch)
   bits.append(h.length_bits)
   ingested_bits.append(h.length_bits//32*32)

data = {'epoch' : ls,
   'date_int' : date_int,
   'date' : date,
   'num_epoch' : num_epoch,
   'bits' : bits,
   'ingested_bits' : ingested_bits,
   }
   
np.save(save_file, data)
