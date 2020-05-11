import time

import QKDController
import chopper
import chopper2
import transferd


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


def main():
    # print(transferd.measure_local_count_rate())
    test_raw_key_gen()
    # test_chopper()
    # QKDController.transferd.start_communication()
    # chopper.start_chopper()
    # QKDController._start_readevents()
    # time.sleep(10)
    # chopper.stop_chopper()
    # QKDController.stop_communication()



if __name__ == '__main__':
    main()
