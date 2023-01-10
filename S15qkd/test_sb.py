from S15qkd.utils import Process
from S15qkd import readevents
import pathlib
Process.load_config()
Process.config.program_root = '/root/programs/qcrypto/remotecrypto'
dir_qcrypto = pathlib.Path(Process.config.program_root)
re = readevents.Readevents(dir_qcrypto / 'readevents')
re.start_sb()
