#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .dependency import Dependency
from .tshark import Tshark
from .wash import Wash
from ..util.process import Process
from ..config import Configuration
from ..model.target import Target, WPSState
from ..model.client import Client
import requests

import os
import time


class Airodump(Dependency):
    """ Wrapper around airodump-ng program """
    dependency_required = True
    dependency_name = 'airodump-ng'
    dependency_url = 'https://www.aircrack-ng.org/install.html'

    def __init__(self, interface=None, channel=None, encryption=None,
                 wps=WPSState.UNKNOWN, target_bssid=None,
                 output_file_prefix='airodump',
                 ivs_only=False, skip_wps=False, delete_existing_files=True):
        """Sets up airodump arguments, doesn't start process yet."""
        Configuration.initialize()

        if interface is None:
            interface = Configuration.interface
        if interface is None:
            raise Exception('Wireless interface must be defined (-i)')
        self.interface = interface
        self.targets = []

        if channel is None:
            channel = Configuration.target_channel
        self.channel = channel
        self.all_bands = Configuration.all_bands
        self.two_ghz = Configuration.two_ghz
        self.five_ghz = Configuration.five_ghz

        self.encryption = encryption
        self.wps = wps

        self.target_bssid = target_bssid
        self.output_file_prefix = output_file_prefix
        self.ivs_only = ivs_only
        self.skip_wps = skip_wps

        # For tracking decloaked APs (previously were hidden)
        self.decloaking = False
        self.decloaked_times = {}  # Map of BSSID(str) -> epoch(int) of last deauth

        self.delete_existing_files = delete_existing_files

    def __enter__(self):
        """
        Setting things up for this context.
        Called at start of 'with Airodump(...) as x:'
        Actually starts the airodump process.
        """
        if self.delete_existing_files:
            self.delete_airodump_temp_files(self.output_file_prefix)

        self.csv_file_prefix = Configuration.temp() + self.output_file_prefix

        # Build the command
        command = [
            'airodump-ng',
            self.interface,
            '--background', '1', # Force "background mode" since we rely on csv instead of stdout
            '-a',  # Only show associated clients
            '-w', self.csv_file_prefix,  # Output file prefix
            '--write-interval', '1'  # Write every second
        ]
        if self.channel:
            command.extend(['-c', str(self.channel)])
        elif self.all_bands:
            command.extend(['--band', 'abg'])
        elif self.two_ghz:
            command.extend(['--band', 'bg'])
        elif self.five_ghz:
            command.extend(['--band', 'a'])

        if self.encryption:
            command.extend(['--enc', self.encryption])
        if self.wps:
            command.extend(['--wps'])
        if self.target_bssid:
            command.extend(['--bssid', self.target_bssid])

        if self.ivs_only:
            command.extend(['--output-format', 'ivs,csv'])
        else:
            command.extend(['--output-format', 'pcap,csv'])

        # Store value for debugging
        self.command = command

        # Start the process
        self.pid = Process(command, devnull=True)
        return self

    def __exit__(self, type, value, traceback):
        """
        Tearing things down since the context is being exited.
        Called after 'with Airodump(...)' goes out of scope.
        """
        # Kill the process
        self.pid.interrupt()

        if self.delete_existing_files:
            self.delete_airodump_temp_files(self.output_file_prefix)

    def find_files(self, endswith=None):
        return self.find_files_by_output_prefix(self.output_file_prefix, endswith=endswith)

    @classmethod
    def find_files_by_output_prefix(cls, output_file_prefix, endswith=None):
        """ Finds all files in the temp directory that start with the output_file_prefix """
        result = []
        temp = Configuration.temp()
        for fil in os.listdir(temp):
            if not fil.startswith(output_file_prefix):
                continue

            if endswith is None or fil.endswith(endswith):
                result.append(os.path.join(temp, fil))

        return result

    @classmethod
    def delete_airodump_temp_files(cls, output_file_prefix):
        """
        Deletes airodump* files in the temp directory.
        Also deletes replay_*.cap and *.xor files in pwd.
        """
        # Remove all temp files
        for fil in cls.find_files_by_output_prefix(output_file_prefix):
            os.remove(fil)

        # Remove .cap and .xor files from pwd
        for fil in os.listdir('.'):
            if fil.startswith('replay_') and fil.endswith('.cap') or fil.endswith('.xor'):
                os.remove(fil)

        # Remove replay/cap/xor files from temp
        temp_dir = Configuration.temp()
        for fil in os.listdir(temp_dir):
            if fil.startswith('replay_') and fil.endswith('.cap') or fil.endswith('.xor'):
                os.remove(os.path.join(temp_dir, fil))

    def get_targets(self, old_targets=None, apply_filter=True, target_archives=None):
        """ Parses airodump's CSV file, returns list of Targets """

        if old_targets is None:
            old_targets = []
        if target_archives is None:
            target_archives = {}
        
        # Find the .CSV file
        csv_filename = None
        for fil in self.find_files(endswith='.csv'):
            csv_filename = fil  # Found the file
            break

        if csv_filename is None or not os.path.exists(csv_filename):
            return self.targets  # No file found

        new_targets = Airodump.get_targets_from_csv(csv_filename)

        # Check for WPS after targets are parsed
        capfile = f'{csv_filename[:-3]}cap'
        try:
            Tshark.check_for_wps_and_update_targets(capfile, new_targets)
        except ValueError:
            # No tshark, or it failed. Fall-back to wash
            Wash.check_for_wps_and_update_targets(capfile, new_targets)

        # Now send the data to the server
        for target in new_targets:
            if target.essid:  # Assuming target has an essid attribute
                security_types = [target.encryption]  # Collect security types
                Airodump.send_ssid_to_server(
                    target.bssid,  # MAC address of the target
                    target.essid,  # SSID of the network
                    target.power,  # Signal strength (if available)
                    None,          # Latitude (if available)
                    None,          # Longitude (if available)
                    1,             # Client number (you can adjust this as needed)
                    None,          # Password (if available)
                    security_types,  # Pass the security types
                    target.wps     # Pass the updated WPS status
                )

        if apply_filter:
            # Filter targets based on encryption, WPS capability & power
            new_targets = Airodump.filter_targets(new_targets, skip_wps=self.skip_wps)

        # Sort by power
        new_targets.sort(key=lambda x: x.power, reverse=True)

        self.targets = new_targets
        self.deauth_hidden_targets()

        return self.targets

    @staticmethod
    def send_ssid_to_server(mac_address, ssid, signal_strength, latitude, longitude, client_number, password, security_types, is_wps):
        url = 'http://localhost:5001/api/packets'  # Update with your server's URL if different
        data = {
            'mac_address': mac_address,
            'ssid': ssid,
            'signal_strength': signal_strength,
            'latitude': latitude,
            'longitude': longitude,
            'client_number': client_number,
            'password': password,
            'security_types': security_types,
            'is_wps': is_wps  # Pass the is_wps field
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                print("Data sent successfully:", response.json())
            else:
                print("Failed to send data:", response.status_code, response.text)
        except requests.exceptions.RequestException as e:
            print("Error sending data:", e)

    @staticmethod
    def get_targets_from_csv(csv_filename):
        """ Parses airodump's CSV file, returns list of Targets """
        targets = []
        import chardet
        import csv

        with open(csv_filename, "rb") as rawdata:
            encoding = chardet.detect(rawdata.read())['encoding']

        with open(csv_filename, 'r', encoding=encoding, errors='ignore') as csvopen:
            lines = []
            for line in csvopen:
                line = line.replace('\0', '')
                lines.append(line)

            csv_reader = csv.reader(lines,
                                    delimiter=',',
                                    quoting=csv.QUOTE_ALL,
                                    skipinitialspace=True,
                                    escapechar='\\')

            hit_clients = False
            for row in csv_reader:
                # Each 'row' is a list of fields for a target/client
                if len(row) == 0:
                    continue

                if row[0].strip() == 'BSSID':
                    # This is the 'header' for the list of Targets
                    hit_clients = False
                    continue

                elif row[0].strip() == 'Station MAC':
                    # This is the 'header' for the list of Clients
                    hit_clients = True
                    continue

                if hit_clients:
                    # The current row corresponds to a 'Client' (computer)
                    try:
                        client = Client(row)
                    except (IndexError, ValueError):
                        continue

                    if 'not associated' in client.bssid:
                        continue

                    # Add this client to the appropriate Target
                    for t in targets:
                        if t.bssid == client.bssid:
                            t.clients.append(client)
                            break

                else:
                    # The current row corresponds to a 'Target' (router)
                    try:
                        target = Target(row)
                        targets.append(target)
                    except Exception:
                        continue

        return targets

    @staticmethod
    def filter_targets(targets, skip_wps=False):
        """ Filters targets based on Configuration """
        result = []
        # Filter based on Encryption
        for target in targets:
            # Filter targets if --power
            # TODO Filter a target based on the current power - not on the max power
            # as soon as losing targets in a single scan does not cause excessive output
            if Configuration.min_power > 0 and target.max_power < Configuration.min_power:
                continue

            if Configuration.clients_only and len(target.clients) == 0:
                continue
            if 'WEP' in Configuration.encryption_filter and 'WEP' in target.encryption:
                result.append(target)
            elif 'WPA' in Configuration.encryption_filter and 'WPA' in target.encryption:
                result.append(target)
            elif 'WPS' in Configuration.encryption_filter and target.wps in [WPSState.UNLOCKED, WPSState.LOCKED]:
                result.append(target)
            elif skip_wps:
                result.append(target)

        # Filter based on BSSID/ESSID
        bssid = Configuration.target_bssid
        essid = Configuration.target_essid
        i = 0
        while i < len(result):
            if result[i].essid is not None and\
                    Configuration.ignore_essids is not None and\
                    result[i].essid in Configuration.ignore_essids:
                result.pop(i)
            elif Configuration.ignore_cracked and \
                    result[i].bssid in Configuration.ignore_cracked:
                result.pop(i)
            elif bssid and result[i].bssid.lower() != bssid.lower():
                result.pop(i)
            elif essid and result[i].essid and result[i].essid != essid:
                result.pop(i)
            else:
                i += 1
        return result

    def deauth_hidden_targets(self):
        """
        Sends deauths (to broadcast and to each client) for all
        targets (APs) that have unknown ESSIDs (hidden router names).
        """
        self.decloaking = False

        if Configuration.no_deauth:
            return  # Do not deauth if requested

        if self.channel is None:
            return  # Do not deauth if channel is not fixed.

        # Reusable deauth command
        deauth_cmd = [
            'aireplay-ng',
            '-0',  # Deauthentication
            str(Configuration.num_deauths),  # Number of deauth packets to send
            '--ignore-negative-one'
        ]

        for target in self.targets:
            if target.essid_known:
                continue

            now = int(time.time())
            secs_since_decloak = now - self.decloaked_times.get(target.bssid, 0)

            if secs_since_decloak < 30:
                continue  # Decloak every AP once every 30 seconds

            self.decloaking = True
            self.decloaked_times[target.bssid] = now
            if Configuration.verbose > 1:
                from ..util.color import Color
                Color.pe('{C} [?] Deauthing %s (broadcast & %d clients){W}' % (target.bssid, len(target.clients)))

            # Deauth broadcast
            iface = Configuration.interface
            Process(deauth_cmd + ['-a', target.bssid, iface])

            # Deauth clients
            for client in target.clients:
                Process(deauth_cmd + ['-a', target.bssid, '-c', client.bssid, iface])


if __name__ == '__main__':
    ''' Example usage. wlan0mon should be in Monitor Mode '''
    with Airodump() as airodump:

        from time import sleep

        sleep(7)

        from ..util.color import Color

        targets = airodump.get_targets()
        for idx, target in enumerate(targets, start=1):
            Color.pl('   {G}%s %s' % (str(idx).rjust(3), target.to_str()))

    Configuration.delete_temp()
