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
            self.quantum_bit_error = qber_numerator / qber_denominator
            self.total_coincidences = results[16]
            self.total_counts = results[17]
        else:
            raise Exception(error)

    def __repr__(self):
        return f'File: {self.epoch_file_path}, QBER: {self.quantum_bit_error}, Total coincidences: {self.total_coincidences}, Total counts: {self.total_counts}'

if __name__ == "__main__":
    diag = RawKeyDiagnosis('b2331bef')
    print(diag.quantum_bit_error)
