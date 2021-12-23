==========
Issues
==========

This page lists stuff that is being worked on.

Hardcoding device name
----------------------

Docker is currently run by passing the device id directly.

.. code-block:: shellscript

  usb-S-Fifteen_Instruments_USB_Counter_TDC1-0019-if00

Meanwhile, readevents4a - the code that talks to the device, expects the 'tty' form.

.. code-block:: shellscript

  ttyARM0
  
Ad-Hoc solution: create a symbolic link to the device file with 'ln -s' in the /dev folder.

To-do: Find a way to dynamically recognise and process devices, either via device id or tty.

