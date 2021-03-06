import time
import os
import numpy as np

import S15QKD.controller as QKDController
from S15QKD import chopper
from S15QKD import chopper2
from S15QKD import transferd
from S15QKD import error_correction


def test_raw_key_gen():
    start = time.time()
    QKDController.start_communication()
    QKDController.transferd.symmetry_negotiation()
    time.sleep(10)
    QKDController.start_raw_key_generation()  # this also tests periode_find
    time.sleep(50)
    QKDController.stop_communication()
    print(f'Start raw key gen test runtime: {str(time.time() - start)} s')


def test_chopper():
    QKDController.start_communication()
    time.sleep(2)
    chopper.start_chopper()
    QKDController._start_readevents()
    time.sleep(15)
    chopper.stop_chopper()
    QKDController.stop_communication()


def test_error_correction_with_test_files():
    QKDController.start_communication()
    # QKDController.symmetry_negotiation()
    error_correction.raw_key_folder = 'data/ec_test_data/rawkeyA'
    error_correction.errcd_killfile_option = ''
    error_correction.start_error_correction()
    f_list = os.listdir(error_correction.raw_key_folder)
    arr = np.array([int(i, 16) for i in f_list])

    for i in arr.argsort():
        print(f_list[i])
        error_correction.ec_queue.put(f_list[i])
    time.sleep(20)
    QKDController.stop_communication()


def main():
	transferd.start_communication()
    # print(transferd.measure_local_count_rate())
    # test_raw_key_gen()
    # test_error_correction_with_test_files()
    # QKDController.transferd.start_communication()
    # test_chopper()
    # QKDController.transferd.start_communication()
    # chopper.start_chopper()
    # QKDController._start_readevents()
    # time.sleep(10)
    # chopper.stop_chopper()
    # QKDController.stop_communication()



if __name__ == '__main__':
    main()
