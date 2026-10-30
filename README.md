Meshmap: a program that simulates data from multiple buoys in the format we are expecting to recieve from the rs485 sensors on the LoRa nodes.

  To run, set a terminal directory to the Meshmap file.
  enter: 
    python simulate.py --reset
  followed by:
    python server.py
  
  A local host should open in your browser with the web app running.
  simulate.py generates data for each buoy and puts it in the database that will be connected to the meshtastic network in the final product.


firmware: the custom meshtastic device firmware.

  Current device: RAK4631
  Enabled modules: RAK5802 rs485 serial module

  I use the PlatformIO extension in VScode to make changes to the files, build, & upload, the firmware to your RAK4631 module. You can also open a serial monitor to get the raw data off the node.
