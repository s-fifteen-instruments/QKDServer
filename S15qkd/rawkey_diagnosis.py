import math
import struct
import subprocess
import json

from .qkd_globals import config_file
with open(config_file, 'r') as f:
    config = json.load(f)
    prog_diagnosis = config['program_root'] + '/diagnosis'

class RawKeyDiagnosis(object):
    """
    Diagnosis of raw key files produced in service mode.
    """
    def __init__(self, epoch_file_path: str):
        diagnosis_process = subprocess.Popen([prog_diagnosis,
                                              '-q', epoch_file_path],
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
        data, error = diagnosis_process.communicate()
        if len(data) != 0:
            self.epoch_file_path = epoch_file_path
            results = list(map(int, data.split()))
            self.coincidences_VV = results[0]
            self.coincidences_VH = results[2]
            self.coincidences_ADAD = results[5]
            self.coincidences_ADD = results[7]
            self.coincidences_HV = results[8]
            self.coincidences_HH = results[10]
            self.coincidences_DAD = results[13]
            self.coincidences_DD = results[15]
            qber_numerator = self.coincidences_HH + self.coincidences_VV + \
                self.coincidences_ADAD + self.coincidences_DD
            qber_denominator = self.coincidences_ADD + self.coincidences_DAD + \
                self.coincidences_HV + self.coincidences_VH + qber_numerator
            self.quantum_bit_error = qber_numerator / (qber_denominator + 1)
            self.total_coincidences = results[16]
            self.total_counts = results[17]
        else:
            raise Exception(error)

    def __repr__(self):
        return f'File: {self.epoch_file_path}, QBER: {self.quantum_bit_error}, Total coincidences: {self.total_coincidences}, Total counts: {self.total_counts}'

    def diagnosis(self, epoch_file_path: str):
        """ Replaces diagnosis.c functionality. #TODO: proper handling/return of errors
        """
        body = []
        matrix = [0] * 16
        garbage1 = 0
        garbage2 = 0
        okcount = 0
        decode = [-1, 0, 1, -1, 2, -1, -1, -1, 3, -1, -1, -1, -1, -1, -1, -1] # translate valid bit values to 4 array index
        header_info_size = 16 # 16 bytes of T3 header https://qcrypto.readthedocs.io/en/documentation/file%20specification.html
        with open(epoch_file_path, 'rb') as f:
            head_info = f.read(header_info_size)
            word = f.read(4)
            while word != b"":
                dat, = struct.unpack('<I', word) # unpacking was done wrongly in original diagnosis.c code.
                dat_bytes = dat.to_bytes(4,'little')
                body.append(dat_bytes[3])
                body.append(dat_bytes[2])
                body.append(dat_bytes[1])
                body.append(dat_bytes[0])
                word = f.read(4)

        tag, epoc, length_entry, bits_per_entry = struct.unpack('iIIi', head_info) #int, unsigned int, unsigned int, int
        if (tag != 0x103 and tag != 3) :
            logger.error(f'{file_name} is not a Type3 header file')
        if hex(epoc) != ('0x' + file_name.split('/')[-1]):
            logger.error(f'Epoch in header {hex(epoc)} does not match epoc filename {file_name}')
        if (bits_per_entry != 8):
            logger.warning(f'Not a service file with 8 bits per entry')

        """ Calculation for number of bytes in original C. multiplication gives total_bits.
            int((total_bits +7) /8) gives the ceiling of total_bits/8. 16 is the header info which is the total number of bytes in epoch.
            Data is packed in 32 bits/4 bytes words.
            int(total bytes/4)+ 1 if (total_bytes & 3) else 0  is another ceiling funciton of total_words/4
            """
        #total_bytes = int((length_entry*bits_per_entry + 7)/8) + 16
        #total_words = int(total_bytes/4) + (1 if (total_bytes & 3) else 0)
        total_bytes = math.ceil((length_entry*bits_per_entry)/8) + header_info_size
        total_words = math.ceil(total_bytes/4)
        if total_words*4 != (len(body) + len(head_info)):
            logger.error(f'stream 3 size inconsistency')
        for i in range(length_entry):
            a = decode[body[i] & 0xf]
            b = decode[(body[i]>>4) & 0xf]
            if a < 0:
                garbage1 += 1
            if b < 0:
                garbage2 += 1;
            if ((a >= 0) and (b >= 0)) :
                matrix[a * 4 + b] += 1
                okcount += 1;
        return matrix, okcount, length_entry, garbage2, garbage1

if __name__ == "__main__":
    diag = RawKeyDiagnosis('b2331bef')
    print(diag.quantum_bit_error)
