echo -e "[*] Setting up the Bluetooth Services for Full Scanning"
sudo btmgmt le on
sudo hciconfig hci0 up
sudo hciconfig hci0 piscan
echo -e "[+] Completed the Bluetooth Services for Full Scanning"
