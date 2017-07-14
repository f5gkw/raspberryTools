#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#    Copyright (C) 2015-2017 framp at linux-tips-and-tricks dot de
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#####################################################################################################
#
# --- Purpose:
#
# Copy user root partition from SD card to another partition (e.g. USB stick or external USB disk)
# and update required files such that from now on the other partition will be used by raspberry
# and SD card is only needed for raspberry boot process 
#
# 1) Valid candidates for new root partition:
#    a) filesystem type has to match
#    b) target partition has to have enough space
#    c) target partition has to be empty
# 2) Backup SD card boot command file cmdline.txt to cmdline.txt.sd
# 3) Update SD card boot command file cmdline.txt to use the new partition from now on
# 5) Copy all files from SD root partition /dev/mmcblk0p2 to target partition
# 6) Update /etc/fstab file on target partition
#
# --- Notes: 
#
# 1) No data is deleted from any partition in any case
# 2) If something went wrong the saved file cmdline.txt.sd on /dev/mmcblk0p1 can be 
#    copied to cmdline.txt and the original SD root partition will be used again on next boot
# 3) If there are multiple USB disks connected the target device partition type has to be gpt instead of mbr 
#
#####################################################################################################
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
# NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND 
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#####################################################################################################

import subprocess
import re
import os
import sys
import logging.handlers
import argparse
import math
import locale
import traceback

MYSELF = os.path.basename(__file__)
MYNAME = os.path.splitext(os.path.split(MYSELF)[1])[0]

VERSION = "0.2.4"    

try:
	GIT_DATE = "$Date$"
	GIT_DATE_ONLY = GIT_DATE.split(' ')[1]
	GIT_TIME_ONLY = GIT_DATE.split(' ')[2]
	GIT_COMMIT = "$Sha1$"
	GIT_COMMIT_ONLY = GIT_COMMIT.split(' ')[1][:-1]

except Exception,e:
	GIT_DATE_ONLY = "1970-01-01"
	GIT_TIME_ONLY = "00:00:00"
	GIT_COMMIT_ONLY = "42424242"

GIT_CODEVERSION = MYSELF + " V" + str(VERSION) + " " + GIT_DATE_ONLY + "/" + GIT_TIME_ONLY + " " + GIT_COMMIT_ONLY

class Singleton:

    def __init__(self, decorated):
        self._decorated = decorated

    def Instance(self):
        try:
            return self._instance
        except AttributeError:
            self._instance = self._decorated()
            return self._instance

    def __call__(self):
        raise TypeError('Singletons must be accessed through `Instance()`.')

    def __instancecheck__(self, inst):
        return isinstance(inst, self._decorated)
        
# return big number human readable in KB, MB ...

def asReadable(number):

	if number is None:
		return "NA"

	if not isinstance(number, float):
		number = float(number)
	
	table = [[4, " TiB"], [3, " GiB"], [2, " MiB"], [1, " KiB"] , [0, " B"]]
	
	v = next(e for e in table if number > math.pow(1024, e[0]))
	return "%.2f%s" % (number / math.pow(1024, v[0]), v[1])

# execute an OS command

def executeCommand(command, noRC=True, dryrun=False):
	global logger
	rc = None
	result = None

	if dryrun:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_COMMAND_EXECUTING,command)			
		result=""
		rc=0
	else:
		try:
			proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
			result,error = proc.communicate()
			rc = proc.returncode		

			if rc != 0 and noRC:
				raise Exception("Command '%s' failed with rc %d\nError message:\n%s" % (command, rc, error.rstrip()))
	
		except OSError, e:
			raise e		 
	
	if noRC:
		return result
	else:	
		return (rc, result)
		
# i18n
	
class MessageCatalog(object):

	# locale.setlocale(locale.LC_ALL, '')

	__locale = locale.getdefaultlocale()[0].upper().split("_")[0] 

# 	__locale = "DE"

	if not __locale in ("DE"):
		__locale = "EN"

	@staticmethod
	def getLocalizedMessage(message, *messageArguments):
		msgEyeCatcher={ "I": "---", "W": "!!!", "E": "???" }
		if not MessageCatalog.__locale in message:
			return message[MessageCatalog.MSG_UNDEFINED].format(message)
		else:
			msg=message[MessageCatalog.__locale].split(' ')
			eyeCatcher=msgEyeCatcher[msg[0][-1]]
			message=msg[0]+" " + eyeCatcher + " " + " ".join(msg[1:])
			return message.format(*messageArguments)

	@staticmethod
	def getDefaultLocale():
		return MessageCatalog.__locale

	@staticmethod
	def setLocale(locale):
		MessageCatalog.__locale=locale.upper()
		return MessageCatalog.__locale

	@staticmethod
	def getSupportedLocales():
		return [ 'EN', 'DE' ]

	@staticmethod
	def isSupportedLocale(locale):
		return locale.upper() in MessageCatalog.getSupportedLocales()
	
	MSG_UNDEFINED = {
                   "EN": "RSD0001E Undefined message for {0}",
                   "DE": "RSD0001E Unbekannte Meldung für {0}" }
	MSG_VERSION = {
                   "EN": "RSD0002I {0}",
                   "DE": "RSD0002I {0}" 
	}
	MSG_DETECTING_PARTITIONS = {
				   "EN": "RSD0003I Detecting partitions",
				   "DE": "RSD0003I Partitionen werden erkannt"
	}
	MSG_DETECTED_PARTITION = {
				   "EN": "RSD0004I {0} - Size: {1} - Free: {2} - Mountpoint: {3} - Partitiontype: {4} - Partitiontable: {5}",
				   "DE": "RSD0004I {0} - Größe: {1} - Frei: {2} - Mountpunkt: {3} - Partitionstyp: {4} - Partitiontabelle: {5}"
	}
	MSG_NO_ELIGIBLE_ROOT = {
				   "EN": "RSD0005E No eligible target root partitions found",
				   "DE": "RSD0005E Keine mögliche Ziel root Partition gefunden"
	}
	MSG_ELIGIBLES_AS_ROOT = {
				   "EN": "RSD0006I Following partitions are eligible as a new root partition",
				   "DE": "RSD0006I Folgende Partitionen sind eine mögliche neue root Partition"
	}
	MSG_ELIGIBLE_AS_ROOT = {
				   "EN": "RSD0007I {0}: {1}",
				   "DE": "RSD0007I {0}: {1}"
	}
	MSG_ENTER_PARTITION = {
				   "EN": "RSD0008I Enter partition name or number: ",
				   "DE": "RSD0008I Partitionsnamen oder eingeben: "
	}
	MSG_PARTITION_INVALIDE = {
				   "EN": "RSD0009E Partition {0} does not exist",
				   "DE": "RSD0009E Partition {0} gibt es nicht"
	}
	MSG_TARGET_PARTITION_CANDIDATES = {
				   "EN": "RSD0010I Target root partition candidates: {0}",
				   "DE": "RSD0010I Ziel root Partitionskandidaten: {0}"
	}
	MSG_ROOT_ALREADY_MOVED = {
				   "EN": "RSD0011E Root partition already moved to {0}",
				   "DE": "RSD0011E Root Partition wurde schon auf {0} umgezogen"
	}
	MSG_SOURCE_ROOT_PARTITION = {
				   "EN": "RSD0012I Source root partition {0}: size: {1} - Used space: {2} - Type: {3}",
				   "DE": "RSD0012I Quell root Partition {0}: Größe: {1} - Benutzter Speicherplatz: {2} - Typ: {3}"
	}	
	MSG_TESTING_PARTITION = {
				   "EN": "RSD0013I Testing partition {0}: Size: {1} - Free space: {2} - Type: {3}",
				   "DE": "RSD0013I Partition {0} wird getestet: Größe: {1} - Freier Speicherplatz: {2} - Typ: {3}",
	}	
	MSG_PARTITION_NOT_MOUNTED = {
				   "EN": "RSD0014W Skipping {0} - Partition is not mounted",
				   "DE": "RSD0014W Partition {0} wird übersprungen - nicht gemounted"
	}	
	MSG_PARTITION_TOO_SMALL = {
				   "EN": "RSD0015W Skipping {0} - Partition is too small with size {1} ",
				   "DE": "RSD0015W Partition {0} wird übersprungen - zu klein mit der Größe {1} "
	}	
	MSG_PARTITION_INVALID_TYPE = {
				   "EN": "RSD0016W Skipping {0} - Partition has incorrect type {1}",
				   "DE": "RSD0016W Partition {0} wird übersprungen - Partitionstyp {1} stimmt nicht"
	}	
	MSG_PARTITION_INVALID_FILEPARTITION = {
				   "EN": "RSD0017W Skipping {0} - Partition has partitiontable type {1} but has to be gpt",
				   "DE": "RSD0017W Partition {0} wird übersprungen - Partition hat Partitionstabellentyp {1} der aber gpt sein muss"
	}	
	MSG_PARTITION_NOT_EMPTY = {
				   "EN": "RSD0018W Skipping {0} - Partition is not empty or there are more directories than /home/pi",
				   "DE": "RSD0018W Partition {0} wird übersprungen - Partition ist nicht leer oder hat nicht nur das /home/pi Verzeichnis"
	}	
	MSG_PARTITION_UNKNOWN_SKIP = {
				   "EN": "RSD0019E Skipping {0} for unknown reasons",
				   "DE": "RSD0019E Partition {0} wird aus unbekannten Gründen übersprungen"
	}				
	MSG_PARTITION_WILL_BE_COPIED = {
				   "EN": "RSD0020I Partition {0} will be copied to partition {1} and become new root partition",
				   "DE": "RSD0020I Partition {0} wird auf Partition {1} kopiert und wird die neue root Partition"
	}				
	MSG_ARE_YOU_SURE = {
				   "EN": "RSD0021I Are you sure (y/N) ? ",
				   "DE": "RSD0021I Bist Du sicher (j/N) ? "
	}				
	MSG_COPYING_ROOT = {
				   "EN": "RSD0022I Copying rootpartition ... Please be patient",
				   "DE": "RSD0022I Rootpartition wir kopiert ... Bitte Geduld"
	}				
	MSG_UPDATING_FSTAB = {
				   "EN": "RSD0023I Updating /etc/fstab on {0}",
				   "DE": "RSD0023I /etc/fstab wird auf {0} angepasst"
	}				
	MSG_SAVING_OLD_CMDFILE = {
				   "EN": "RSD0024I Saving {0} on {1} as {2}",
				   "DE": "RSD0024I {0} wird auf {1} als {2} gesichert"
	}				
	MSG_UPDATING_CMDFILE = {
				   "EN": "RSD0025I Updating {0} on {1}",
				   "DE": "RSD0025I {0} wird auf {1} angepasst"
	}				
	MSG_DONE = {
				   "EN": "RSD0026I Finished moving root partition from {0} to partition {1}",
				   "DE": "RSD0026I Umzug von root Partition von {0} auf Partition {1} beendet"
	}				
	MSG_FAILURE = {
				   "EN": "RSD0027E Unexpected exception caught: '{0}'.\nSee log file {1} for details",
				   "DE": "RSD0027E Unerwartete Ausnahme: '{0}'.\nIn Logfile {1} finden sich weitere Fehlerdetails"
	}				
	MSG_NEEDS_ROOT = {
				   "EN": "RSD0028E Script has to be invoked as root or with sudo",
				   "DE": "RSD0028E Das Script muss als root oder mit sudo aufgerufen werden" 
	}
	MSG_ROOTPARTITION_NOT_ON_SDCARD = {
				   "EN": "RSD0029E Current root partition {0} is not located on SD card any more",
				   "DE": "RSD0029E Die aktuelle Rootpartition {0} befindet sich nicht mehr auf der SD Karte"
	}
	MSG_TARGET_PARTITION_SMALLER_THAN_SOURE_PARTITION = {
				   "EN": "RSD0030W Partition {0} has only {1} free space and is smaller than root partition of size {2}",
				   "DE": "RSD0030W Partition {0} hat nur {1} freien Speicherplatz und ist kleiner als die root Partition fer Größe {2}"
	}
	MSG_PARTITION_FREE_SPACE_TOO_SMALL = {
				   "EN": "RSD0031W Skipping {0} - Partition is too small with {1} free space",
				   "DE": "RSD0031W Partition {0} wird übersprungen - zu klein mit {1} freiem Speicherplatz"
	}	
	MSG_PARTITION_TOO_SMALL_BUT_FREE_OK = {
				   "EN": "RSD0032W Skipping {0}. Partition is too small with partition size {1}. But there is enough free space of {2}. Use option --force to enable this partition",
				   "DE": "RSD0032W Partition {0} wird übersprungen.  Zu klein mit der Partitionsgröße {1}. Es ist aber genügend Platz von {2} frei. Benutze Option --force um diese Partition auswählen zu können"
	}
	MSG_INVALID_LOG_LEVEL = {
				   "EN": "RSD0033E Invalid loglevel {0}. Use option -h to list possible arguments",
				   "DE": "RSD0033E Ungültiger Loglevel {0}. Option -h zeigt die möglichen Argumente"
	}
	MSG_INVALID_LANGUAGE = {
				   "EN": "RSD0034E Invalid language {0}. Use option -h to list possible arguments",
				   "DE": "RSD0034E Ungültige Sprache {0}. Option -h zeigt die möglichen Argumente"
	}	
	MSG_NO_CMDLINE_FOUND = {
				   "EN": "RSD0035E {0} does not exist",
				   "DE": "RSD0035E {0} existiert nicht"
	}	
	MSG_FOUND_IN_FSTAB = {
				   "EN": "RSD0036W Target partition {0} already used in fstab. Commenting out this line",
				   "DE": "RSD0036W Zielpartition {0} wird in der fstab schon benutzt. Die Zeile wird auskommentiert"
	}
	MSG_DRYRUN = {
				   "EN": "RSD0037I Note: Commands will not be executed but listed",
				   "DE": "RSD0037I Hinweis: Befehle werden nicht ausgeführt aber angezeigt"
	}
	MSG_COMMAND_EXECUTING = {
				   "EN": 'RSD0038I Executing command "{0}"',
				   "DE": 'RSD0038I Befehl "{0}" wird ausgeführt'
	}


class Partition(object):
	def __init__(self, name, type=""):
		self.__initialName=name
		if name.startswith("/dev"):
			self.__deviceName=name
			self.__initialUUID=False
		else:
			self.__partUUID=name
			self.__initialUUID=True

		if type == "":
			self.__partType = DeviceManager.Instance().getType(self.__deviceName)
		else:
			self.__partType = type

	def getInitialName(self):
		return self.__initialName
						
	def getDeviceName(self):
		try: 
			return self.__deviceName
		except AttributeError:
			self.__deviceName=DeviceManager.Instance().getDeviceName(name)								
		return self.__deviceName
	
	def getPartUUID(self):
		try:
			return self.__partUUID
		except AttributeError:
			self.__partUUID = DeviceManager.Instance().getPartUUID(self.getDeviceName())
		return self.__partUUID

	def getPartType(self):
		try:
			return self.__partType
		except AttributeError:
			self.__partType = DeviceManager.Instance().getPartType(self.getDeviceName())
		return self.__partType
	
	def hasPartUUID(self):
		return self.getPartUUID()!=""

	def isInitialUUID(self):
		return self.__initialUUID

	def isSDPartition(self):
		return self.getDeviceName().startswith(SSD_DEVICE)
	
	def __eq__(self, other):
		if isinstance(other, Partition):
			return self.__deviceName == other.getDeviceName()
		if isinstance(other, str):
			return self.__deviceName == other				
		return NotImplemented	
       
	def __str__(self):
		if self.hasPartUUID():
			return "%s: Type: %s PARTUUID: %s" % (self.__deviceName,self.__partType, self.__partUUID)
		else:
			return "%s: Type: %s" % (self.__deviceName,self.__partType) 
			
# baseclass for all the linux commands dealing with partitions

class BashCommand(object):
	
	__SPLIT_PARTITION_REGEX = "(/dev/mmcblk0p|/dev/[a-zA-Z]+)([0-9]+)"		

	def __init__(self, command):
		self.__command = command
		self._commandResult = None
		self.__executed = False
		
	def __collect(self):
		if not self.__executed:
			self._commandResult = executeCommand(self.__command)
			self._commandResult = self._commandResult.splitlines()
			self._postprocessResult()
			self.__executed = True			
		
	def getResult(self):
		self.__collect()
		return self._commandResult

	def _postprocessResult(self):
		pass
	
	def _splitPartition(self, partition):
		if isinstance(partition,Partition):		
			m = re.match(self.__SPLIT_PARTITION_REGEX, partition.getDeviceName())
		else:
			m = re.match(self.__SPLIT_PARTITION_REGEX, partition)
		if m:
			return (m.group(1), m.group(2))
		else:
			raise Exception("Unable to split partition %s into device and partition number" % (partition))
	
'''
root@raspi4G:~# df -T
Filesystem	 Type	 1K-blocks	Used Available Use% Mounted on
rootfs		 rootfs	 3683920 2508276	968796  73% /
/dev/root	  ext4	   3683920 2508276	968796  73% /
devtmpfs	   devtmpfs	244148	   0	244148   0% /dev
tmpfs		  tmpfs		49664	 236	 49428   1% /run
tmpfs		  tmpfs		 5120	   0	  5120   0% /run/lock
tmpfs		  tmpfs		99320	   0	 99320   0% /run/shm
/dev/mmcblk0p1 vfat		 57288	9864	 47424  18% /boot
'''

class df(BashCommand):
	
	def __init__(self):
		BashCommand.__init__(self, 'df -T')
		self.fileSystem = []
		
	def _postprocessResult(self):
		self._commandResult = self._commandResult[1:]
		
	def __mapRootPartition(self, partition):
		if partition == ROOT_PARTITION.getDeviceName():
			return ROOTFS
		else:
			return partition
			
	def getSize(self, partition):
		partition = self.__mapRootPartition(partition)
		for line in self.getResult():
			lineElements = line.split()
			if lineElements[0] == partition:
				return int(lineElements[3])*1024

	def getFree(self, partition):
		partition = self.__mapRootPartition(partition)
		for line in self.getResult():
			lineElements = line.split()
			if lineElements[0] == partition:
				return int(lineElements[4])*1024

	def getType(self, partition):
		partition = self.__mapRootPartition(partition)
		for line in self.getResult():
			lineElements = line.split()
			if lineElements[0] == partition:
				return lineElements[1]
			
'''
root@raspi4G:~# lsblk -rnb
sda 8:0 1 4127195136 0 disk 
sda1 8:1 1 4126129664 0 part 
mmcblk0 179:0 0 3963617280 0 disk 
mmcblk0p1 179:1 0 58720256 0 part /boot
mmcblk0p2 179:2 0 3900702720 0 part /
'''
class lsblk(BashCommand):
	def __init__(self):
		BashCommand.__init__(self, 'lsblk -rnb')
					
	def getSize(self, filesystem):
		for line in self.getResult():
			lineElements = line.split()
			if '/dev/' + lineElements[0] == filesystem:
				return int(lineElements[3])

	def getMountpoint(self, filesystem):
		for line in self.getResult():
			lineElements = line.split()
			if '/dev/' + lineElements[0] == filesystem:
				if len(lineElements) == 7:				
					return lineElements[6]
				else:
					return None
		return None
			
	def getPartitions(self):
		result = {}
		for line in self.getResult():
			lineElements = line.split()
			result[lineElements[0]]=Partition(lineElements[0])
		return result
	
'''
root@raspi4G:~# fdisk -l

Disk /dev/mmcblk0: 3963 MB, 3963617280 bytes
4 heads, 16 sectors/track, 120960 cylinders, total 7741440 sectors
Units = sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disk identifier: 0x000981cb

        Device Boot      Start         End      Blocks   Id  System
/dev/mmcblk0p1            8192      122879       57344    c  W95 FAT32 (LBA)
/dev/mmcblk0p2          122880     7741439     3809280   83  Linux

Disk /dev/sda: 4127 MB, 4127195136 bytes
94 heads, 60 sectors/track, 1429 cylinders, total 8060928 sectors
Units = sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disk identifier: 0x00000000

   Device Boot      Start         End      Blocks   Id  System
/dev/sda1               1     8060927     4030463+  ee  GPT

'''		
class fdisk(BashCommand):
	def __init__(self):
		BashCommand.__init__(self, 'fdisk -l 2>/dev/null')
		
	def _postprocessResult(self):
		self._commandResult = filter(lambda line: line.startswith('/dev/'), self._commandResult)
			
	def getSize(self, filesystem):
		for line in self.getResult():
			lineElements = line.split()
			if lineElements[0] == filesystem:
				return int(lineElements[3])
			
	def getPartitions(self):
		result = {}
		for line in self.getResult():
			lineElements = line.split()
			result[lineElements[0]]=Partition(lineElements[0])
		return result

'''
root@raspi4G:~# parted -l -m /dev/sda
BYT;
/dev/sda:4127MB:scsi:512:512:msdos:USB2.0 FlashDisk;
1:1049kB:4127MB:4126MB:ext4::;

BYT;
/dev/mmcblk0:3964MB:sd/mmc:512:512:msdos:SD SR04G;
1:4194kB:62.9MB:58.7MB:fat16::lba;
2:62.9MB:3964MB:3901MB:ext4::;
'''

class parted(BashCommand):
	def __init__(self):
		BashCommand.__init__(self, 'parted -l -m')
		
	def _postprocessResult(self):
		self._commandResult = filter(lambda line: line.startswith('/dev/'), self._commandResult)
			
	def getPartitiontableType(self, partition):
		(partition, partitionNumber) = self._splitPartition(partition)
		if partition.startswith(SSD_DEVICE_CARD):
			partition = SSD_DEVICE_CARD
		for line in self.getResult():
			lineElements = line.split(':')
			if lineElements[0] == partition:
				return lineElements[5]
		return None

	def isGPT(self, partition):
		return self.getPartitiontableType(partition) == "gpt"

	def isMBR(self, partition):
		return not self.isGPT(self, partition)			
		
'''
root@raspi4G:~# sgdisk -i 1 /dev/sda 
GPT fdisk (gdisk) version 0.8.5

Partition table scan:
  MBR: protective
  BSD: not present
  APM: not present
  GPT: present

Found valid GPT with protective MBR; using GPT.

Command (? for help): Using 1
Partition GUID code: 0FC63DAF-8483-4772-8E79-3D69D8477DE4 (Linux filesystem)
Partition unique GUID: AC9DC34D-BAF0-44D6-A682-610CB651E0CA
First sector: 2048 (at 1024.0 KiB)
Last sector: 8060894 (at 3.8 GiB)
Partition size: 8058847 sectors (3.8 GiB)
Attribute flags: 0000000000000000
Partition name: 'Linux filesystem'
'''
	
class sgdisk(BashCommand):
	def __init__(self, partition):
		(partition, partitionNumber) = self._splitPartition(partition)
		BashCommand.__init__(self, 'sgdisk -i %s %s' % (partitionNumber, partition))
		
	def _postprocessResult(self):
		self._commandResult = filter(lambda line: line.startswith('Partition unique'), self._commandResult)
						
	def getGUID(self):
		if len(self.getResult()) > 0: 
			lineElements = self.getResult()[0].split()
			return lineElements[3]
		else:
			return None
		
	def hasGUID(self):
		return self.getGUID() is not None
		
'''
root@raspi4G:~# blkid
/dev/mmcblk0p1: LABEL="boot" UUID="0763-6493" TYPE="vfat" PARTUUID="775d7214-01"
/dev/mmcblk0p2: UUID="db3c7508-ce47-4b20-b1da-a1ac4446755c" TYPE="ext4" PARTUUID="775d7214-02"
/dev/sdb1: UUID="582f0522-3c72-4e4c-a327-435caa23c212" TYPE="ext4" PARTLABEL="Linux filesystem" PARTUUID="9aec15d8-65bc-4c55-84e8-f2024eae2ce9"
/dev/sda2: UUID="64047412-cc47-422c-b458-35e9fa69f1f9" TYPE="ext4" PARTUUID="0683fbcd-02"
/dev/sda1: LABEL="boot" UUID="70CE-EB76" TYPE="vfat" PARTUUID="0683fbcd-01"
/dev/mmcblk0: PTUUID="775d7214" PTTYPE="dos"
'''
	
class blkid(BashCommand):
	def __init__(self):
		BashCommand.__init__(self, 'blkid')                         
		
	def getType(self, filesystem):
		for line in self.getResult():
			lineElements = line.split()
			fs = lineElements[0][:-1]
			if (fs) == filesystem:
				regex = ".*TYPE=\"([^\"]*)\""		
				m = re.match(regex, line)				
				if m:
					return m.group(1)								
		return None

	def getPartUUID(self, filesystem):
		for line in self.getResult():
			lineElements = line.split()
			fs = lineElements[0][:-1]
			if (fs) == filesystem:
				regex = ".*PARTUUID=\"([^\"]*)\""		
				m = re.match(regex, line)				
				if m:
					return m.group(1)								
		return None

	def getDeviceName(self, partuuid):
		for line in self.getResult():
			regex = ".*PARTUUID=\"([^\"]*)\""		
			m = re.match(regex, line)				
			if m and m.group(1) == partuuid:
				lineElements = line.split()							
				return lineElements[0][:-1]
			
		return None
	
	def getDevices(self):
		devices = []   		
		for line in self.getResult():
			lineElements = line.split()
			partition = lineElements[0][:-1]
			if not partition.startswith(SSD_DEVICE_CARD):
				devices.append(self._splitPartition(partition)[0])
		
		return list(set(devices))

# Facade for all the various device/partition commands available on Linux

@Singleton	
class DeviceManager():
	
	def __init__(self):
		
		self.__df = df()
		self.__blkid = blkid()
		self.__lsblk = lsblk()
		self.__fdisk = fdisk()
		self.__parted = parted()
		self.__partitions = None
		
	def getPartitions(self):
		
		if self.__partitions == None:
			self.__partitions=self.__fdisk.getPartitions()
		return self.__partitions
	
	def getSize(self, partition):
		return self.__df.getSize(partition.getDeviceName())
	
	def getFree(self, partition):
		return self.__df.getFree(partition.getDeviceName())
	
	def getType(self, partition):
		return self.__blkid.getType(partition)

	def getPartUUID(self, partition):
		return self.__blkid.getPartUUID(partition)
	
	def getMountpoint(self, partition):
		return self.__lsblk.getMountpoint(partition)
	
	def getDevices(self):
		return self.__blkid.getDevices()
	
	def isGPT(self, partition):
		return self.__parted.isGPT(partition)
		
	def getGUID(self, partition):
		return sgdisk(partition).getGUID()
	
	def getPartitiontableType(self, partition):
		return self.__parted.getPartitiontableType(partition)

	'''
	root@raspi4G:~# cat /boot/cmdline.txt
	dwc_otg.lpm_enable=0 console=ttyAMA0,115200 kgdboc=ttyAMA0,115200 console=tty1 root=/dev/mmcblk0p2 rootfstype=ext4 elevator=deadline rootwait
	dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=13f4a298-02 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait
	'''
	
	def getSDPartitions(self):
		
		if not os.path.exists(CMD_FILE):
			print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_NO_CMDLINE_FOUND, CMD_FILE)
			sys.exit(-1)
			
		result = executeCommand('cat ' + CMD_FILE)

		regex = ".*root=(PARTUUID=)?(.*) .*rootfstype=([0-9a-zA-Z]+)"		
		m = re.match(regex, result,re.IGNORECASE)				
		if m:
			rootPartition = m.group(2)
			rootFilesystemType = m.group(3)
		else:
			raise Exception("Unable to detect rootPartition and/or rootfstype in %s" % (CMD_FILE))		
		
		return Partition(rootPartition, type=rootFilesystemType)
	
	def getAllDetected(self):
		partitions = self.getPartitions()
		details = []
		for key,partition in partitions.iteritems():
			size = self.getSize(partition)
			free = self.getFree(partition)
			mountpoint = self.getMountpoint(partition)
			partitiontype = self.getType(partition)
			partitionTabletype = self.getPartitiontableType(partition)
			details.append([partition, size, free, mountpoint, partitiontype, partitionTabletype])
		return details

# stderr and stdout logger 

class MyLogger(object):
	def __init__(self, stream, logger, level):
		self.stream = stream
		self.logger = logger
		self.level = level

	def write(self, message):
		self.stream.write(message)
		if len(message.rstrip()) > 1:
			self.logger.log(self.level, message.rstrip())

# detect all available partitions on system

def collectEligiblePartitions():

	global logger 
	global ROOT_PARTITION
	
	cmdPartition = DeviceManager.Instance().getSDPartitions()
	logger.debug("cmdPartition %s" % (cmdPartition))
	logger.debug("ROOT_PARTITION %s" % (ROOT_PARTITION))

	if not cmdPartition.isSDPartition:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ROOTPARTITION_NOT_ON_SDCARD, cmdPartition.getDeviceName())
		sys.exit(-1)
		
	availableTargetPartitions = []
	
	for partition in dm.getPartitions():
		if not partition.getDeviceName().startswith(SSD_DEVICE):
			if partition.getPartType() != cmdPartition.getPartType():
				print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_INVALID_TYPE, partition.getDeviceName(), partition.getPartType())
			else:
				availableTargetPartitions.append(partition)

	availableTargetPartitionNames = [ p.getDeviceName() for p in availableTargetPartitions ]
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_TARGET_PARTITION_CANDIDATES, ' '.join(availableTargetPartitionNames))
	
	sourceRootPartition = cmdPartition
	sourceRootType = dm.getType(cmdPartition)
	sourceRootSize = dm.getSize(cmdPartition)
	sourceRootFree = dm.getFree(cmdPartition)
	sourceRootUsed = sourceRootSize - sourceRootFree

	logger.debug("cmdPartition: %s\nsourceRootPartition: %s" % (cmdPartition,sourceRootPartition))
	
	if not cmdPartition.isSDPartition():
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ROOT_ALREADY_MOVED, cmdPartition)
		sys.exit(-1) 

	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_SOURCE_ROOT_PARTITION, sourceRootPartition.getDeviceName(), asReadable(sourceRootSize), asReadable(sourceRootUsed), sourceRootType)
		
	validTargetPartitions = []

	multipleDevices = len(dm.getDevices()) > 1  
						
	for partition in availableTargetPartitions:

		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_TESTING_PARTITION, partition.getDeviceName(), asReadable(dm.getSize(partition)), asReadable(dm.getFree(partition)), dm.getType(partition))
		partitionMountPoint = dm.getMountpoint(partition)
		logger.debug("partitionMountPoint: %s" % (partitionMountPoint))

		if partitionMountPoint is None:
			print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_NOT_MOUNTED, partition.getDeviceName())

		elif dm.getSize(partition) < sourceRootSize:
			if not force:
				if dm.getSize(partition) < sourceRootSize and dm.getFree(partition) < sourceRootUsed:
					print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_TOO_SMALL, partition.getDeviceName(), asReadable(dm.getSize(partition)))							
				else:
					print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_TOO_SMALL_BUT_FREE_OK, partition.getDeviceName(), asReadable(dm.getSize(partition)), asReadable(dm.getFree(partition)))
					
			else:
				if dm.getFree(partition) < sourceRootUsed:
					logger.debug("free(%s): %s - sourceRootUsed: %s" % (partition, dm.getFree(partition), sourceRootUsed))
					print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_FREE_SPACE_TOO_SMALL, partition.getDeviceName(), asReadable(dm.getFree(partition)))			
				else:
					logger.debug("free(%s): %s - sourceRootSize: %s" % (partition, dm.getFree(partition), sourceRootSize))
					print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_TARGET_PARTITION_SMALLER_THAN_SOURE_PARTITION, partition.getDeviceName(), asReadable(dm.getFree(partition)), asReadable(sourceRootSize))
					validTargetPartitions.append(partition)

		elif dm.getType(partition) != sourceRootType:
			logger.debug("type(%s): %s - sourceRootSize: %s" % (partition.getDeviceName(), dm.getType(partition), sourceRootSize))
			print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_INVALID_TYPE, partition.getDeviceName(), dm.getType(partition))

		elif multipleDevices and not dm.isGPT(partition):
			print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_INVALID_FILEPARTITION, partition.getDeviceName(), dm.getPartitiontableType(partition))

		elif partition != sourceRootPartition:
			diskFilesTgt = int(executeCommand('ls -A ' + partitionMountPoint + ' | wc -l'))
			lostDir = int(executeCommand('ls -A ' + partitionMountPoint + ' | grep -i lost | wc -l'))
			piHome = os.path.exists(partitionMountPoint + '/home/pi')
			logger.debug("disksFilesTgt: %s - lostDir: %s - piHome %s" % (diskFilesTgt, lostDir, piHome))
			
			if (diskFilesTgt == 1 and lostDir == 1) or (lostDir == 0 and diskFilesTgt == 0) or piHome:
				validTargetPartitions.append(partition)
			else:
				print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_NOT_EMPTY, partition.getDeviceName())

		else:
			print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_UNKNOWN_SKIP, partition.getDeviceName())
							
	return validTargetPartitions, sourceRootPartition 
			
##################################################################################
################################### Main #########################################
##################################################################################

# various constants

SSD_DEVICE_CARD = "/dev/mmcblk0"
SSD_DEVICE = SSD_DEVICE_CARD + "p"
BOOT_PARTITION = Partition(SSD_DEVICE + "1")
ROOT_PARTITION = Partition(SSD_DEVICE + "2")
CMD_FILE = "/boot/cmdline.txt"
ROOTFS = "/dev/root"

LOG_FILENAME = "./%s.log" % MYNAME
LOG_LEVEL = logging.INFO 
force=False
dryrun=False

logLevels = { "INFO": logging.INFO , "DEBUG": logging.DEBUG, "WARNING": logging.WARNING }

parser = argparse.ArgumentParser(description="Move SD root partition to external partition on Raspberry Pi")
parser.add_argument("-l", "--log", help="log file (default: " + LOG_FILENAME + ")")
parser.add_argument("-d", "--debug", help="debug level %s (default: %s)" % ('|'.join(logLevels.keys()), logLevels.keys()[logLevels.values().index(LOG_LEVEL)]))
parser.add_argument("-n", "--dryrun", help="dry run. Don't execute any commands but display them",action='store_true')
parser.add_argument("-g", "--language", help="message language %s (default: %s)" % ('|'.join(MessageCatalog.getSupportedLocales()), MessageCatalog.getDefaultLocale()))
parser.add_argument("-f", "--force", help="allow target partitions which are smaller than the source partition", action='store_true')

args = parser.parse_args()
if args.log:
	LOG_FILENAME = args.log

if args.language:
	if MessageCatalog.isSupportedLocale(args.language):
		MessageCatalog.setLocale(args.language)
	else:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_INVALID_LANGUAGE, args.language)
		sys.exit(-1)

if args.debug:
	if args.debug in logLevels:
		LOG_LEVEL = logLevels[args.debug]
	else:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_INVALID_LOG_LEVEL, args.debug)
		sys.exit(-1)

if args.force:
	force=True	

if args.dryrun:
	dryrun=True
	
# setup logging

if os.path.isfile(LOG_FILENAME):
	os.remove(LOG_FILENAME)
	
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, backupCount=1)
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

sys.stdout = MyLogger(sys.stdout, logger, logging.INFO)
sys.stderr = MyLogger(sys.stderr, logger, logging.ERROR)

# doit now

if os.geteuid() != 0: 
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_NEEDS_ROOT)
  	sys.exit(-1)

try:

	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_VERSION, GIT_CODEVERSION)
	
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_DETECTING_PARTITIONS)
	partitions = DeviceManager.Instance().getAllDetected()
	for partition in partitions:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_DETECTED_PARTITION, partition[0].getDeviceName(), asReadable(partition[1]), asReadable(partition[2]), partition[3], partition[4], partition[5])
		
	(validTargetPartitions, sourceRootPartition) = collectEligiblePartitions()
	
	if len(validTargetPartitions) == 0:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_NO_ELIGIBLE_ROOT)
		sys.exit(-1)
	
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ELIGIBLES_AS_ROOT)
	i=1
	for partition in validTargetPartitions:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ELIGIBLE_AS_ROOT, i, partition.getDeviceName())
		i+=1

	if dryrun:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_DRYRUN)
		
	inputAvailable = False
	while not inputAvailable:	
		targetRootPartitionSelected = raw_input(MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ENTER_PARTITION))
		if targetRootPartitionSelected.isdigit() and int(targetRootPartitionSelected) >= 1 and int(targetRootPartitionSelected) <= len(validTargetPartitions):
			targetRootPartitionSelected = validTargetPartitions[int(targetRootPartitionSelected)-1]
			inputAvailable=True
		else:
			inputAvailable = targetRootPartitionSelected in validTargetPartitions
			if not inputAvailable:
				print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_INVALIDE, targetRootPartitionSelected)
	
	dm = DeviceManager()				
	
	sourceDirectory = dm.getMountpoint(sourceRootPartition)
	targetDirectory = dm.getMountpoint(targetRootPartitionSelected)
	logger.debug("sourceDirectory: %s - targetDirectory: %s" % (sourceDirectory, targetDirectory))

	if dryrun:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_DRYRUN)
	
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_PARTITION_WILL_BE_COPIED, sourceRootPartition.getDeviceName(), targetRootPartitionSelected.getDeviceName())
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_ARE_YOU_SURE)
		
	selection = raw_input('')
	if selection not in ['Y', 'y', 'J', 'j']:
		sys.exit(0)
	
	command = "tar cf - --one-file-system --checkpoint=1000 %s | ( cd %s; tar xfp -)" % (sourceDirectory, targetDirectory)
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_COPYING_ROOT)
	executeCommand(command,dryrun=dryrun)
	
	if dm.isGPT(targetRootPartitionSelected):
		targetID = "PARTUUID=" + dm.getGUID(targetRootPartitionSelected)	
	else:
		targetID = targetRootPartitionSelected.getDeviceName()
		
	logger.debug("targetID: %s " % (targetID))

	# check if root partition is already used in fstab
	command = 'grep -q "%s" %s/etc/fstab' % (targetRootPartitionSelected, targetDirectory)
	(rc, result) = executeCommand(command, noRC = False)
	if rc == 0:
		print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_FOUND_IN_FSTAB, targetRootPartitionSelected)
		command = 'sed -i "s|^%s|# commented out by %s|g" %s/etc/fstab' % (targetRootPartitionSelected, MYNAME, targetDirectory)
		executeCommand(command,dryrun=dryrun)
	
	# change /etc/fstab on target
	
	sourceRootPartitionName = sourceRootPartition.getInitialName()
	if sourceRootPartition.isInitialUUID():
		sourceRootPartitionName = "PARTUUID="+sourceRootPartitionName 
	
	command = "sed -i \"s|%s|%s|\" %s/etc/fstab" % (sourceRootPartitionName, targetID, targetDirectory)
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_UPDATING_FSTAB, targetRootPartitionSelected)
	executeCommand(command,dryrun=dryrun)
	
	# create backup copy of old cmdline.txt
	command = "cp -a %s %s; chmod -w %s" % (CMD_FILE, CMD_FILE+".sd", CMD_FILE+".sd")	
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_SAVING_OLD_CMDFILE, CMD_FILE, sourceRootPartition.getDeviceName(), CMD_FILE+".sd")
	executeCommand(command,dryrun=dryrun)
	
	# update cmdline.txt	
	command = "sed -i \"s|root=[^ ]\+|root=%s|g\" %s" % (targetID, CMD_FILE)
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_UPDATING_CMDFILE, CMD_FILE, targetRootPartitionSelected)
	executeCommand(command,dryrun=dryrun)
	
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_DONE, sourceRootPartition.getDeviceName(), targetRootPartitionSelected)

except KeyboardInterrupt as ex:
	print 
	pass	

except Exception as ex:
	logger.error(traceback.format_exc())
	print MessageCatalog.getLocalizedMessage(MessageCatalog.MSG_FAILURE, ex.message, LOG_FILENAME)
