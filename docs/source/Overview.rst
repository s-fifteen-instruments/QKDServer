=========
Overview
=========

QKDServer takes care of the s-fifteen QKD-based key generation business logic. It ties together the quantum channel and the classical channel 
and generates encryption keys ready for consumption.

The implementation of the quantum channel is done via the qcrypto stack (written in C). Python wrappers are used to translate their functionalities into Python.
Each .py file has its twin .c file under qcrypto.

QKDServer is dockerized.
