=========
Overview
=========

QKDServer takes care of the S-Fifteen's QKD-based key generation business logic. It ties together the quantum channel and the classical channel 
and generates encryption keys ready for consumption.

The implementation of the quantum channel is done via the qcrypto stack (written in C). Python wrappers are used to translate their functionalities into Python.
Each .py file has its twin .c file under qcrypto.

In this initial version of QKDServer, only two party QKD key generation  is implemented. QKDServer is also dockerized, like `Guardian <guardian.readthedocs.io>`_ and will generate keys to be used by it. 




