# !/usr/bin/python
#
# Purpose: This script uses rclone to copy over files from
# source to destination. Files that are larger than a pre-defined
# value are chunked into pieces and rcloned individually.
#
# Requirements: Python 3.x, Rclone (already set up via rclone config)
# Tested on: Win 10, Mac OS (15.x - Catalina) and Linux (Debian, Synology DSM)
#
# Usage: Use on your NAS or other system to backup data to
# a cloud-based service that has a limitation of max file
# size, such as Box. Chunk files are stored on the source under .rclone folder.
# This means that extra space is required on the NAS to store the chunks.
#
# Features: Max file size can be changed even when large files
# have already been chunked. Every time the script runs every
# file and chunk file is verified for integrity and a match with
# the user-defined chunk size. If the verification fails
# then the chunks are deleted (on source + destination) and
# new chunks are created from the original large file.
#
# ==================================
# MODIFY THE BELOW TO FIT YOUR NEEDS
# ==================================

# Example paths on Windows
#root_dir = "C:\\SWSETUP\\MY_DATA"
#log_folder = "C:\\SWSETUP"

# Example paths on Linux / Mac
# root_dir = "/tmp/my_data"
# log_folder = "/var/log"


root_dir = ""
log_folder = ""
max_single_file_size = 1200000000 #1200 MB # Shown in bytes. Defined a bit lower than what Box allows.

# The rclone_service_name is how you define the service in your rclone config
rclone_service_name = "box"
rclone_program_location = "/usr/local/bin" # On Mac the default path is /usr/local/bin . For Windows enter it with double \\
# Folder on the remote service to copy the files to
rclone_dest_folder = ""
# Do you want upload the log file to the same remote service (e.g. Box) - yes/no
upload_logs_to_dest="yes"
# destination folder where to place the logs
dest_logs_path=""

# Define a from email address that runs on Gmail.
email_from="email@gmail.com"
# The password is hard-coded in this script, hence why a non-org email is being used with an app pwd.
email_from_pwd = "mypasswd"

# Multiple recipients can be defined - ["a@a.com", "b@b.com"] - remember to include ""
email_to=["email@gmail.com"]
email_subject="rClone encoutered issues"
email_text="Hi, the latest backup encoutered errors.\nPlease review the logs in the attachment."

# Define at what hour of the day should the script gracefully finished (0-23). Comment out if not needed.
hour_to_gracefully_finish="19"

# What to do if the script is already running in the background (0 = run on top, 1 = do not run, 2 = kill the previous process)
what_if_already_running=1

buf_size = 2000000000 # 2 GB # Shown in bytes - how much RAM can be allocated to the zipping process.

# Add extensions as you see fit. .rclone is an actual folder with chunks in it and does not need to be included.
extensions_to_skip = [".bundle", ".tmp", ".temp", ".rclone", ".DS_Store"]

# =============
# NOTES & TO-DO
# =============
#
# To-do:
# =====
# - Should adapt subprocess for the removal of a file (rclone deletefile) instead of using os.remove
# - Check if the email_to is defined and if not, do not execute the mail_log function
#
# Sources:
# ========
#   - Rclone - https://rclone.org/commands/rclone_copyto/
#   - Recursive checks - https://stackoverflow.com/questions/2212643/python-recursive-folder-read
#   - File extension checks - https://stackoverflow.com/questions/5899497/how-can-i-check-the-extension-of-a-file
#   - Zipping files - https://docs.python.org/3/library/zipfile.html
#   - Splitting zip files - https://stackoverflow.com/questions/22751000/split-large-text-filearound-50gb-into-multiple-files/22752317
#   - File matching to determine chunks - https://stackoverflow.com/questions/3964681/find-all-files-in-a-directory-with-extension-txt-in-python/3964696
#   - File matching method no.2 - https://stackoverflow.com/questions/22812785/use-endswith-with-multiple-extensions
#   - List of file extensions to skip - https://www.programcreek.com/python/example/60/os.walk
#   - File size comparisons - https://stackoverflow.com/questions/18351951/check-if-string-ends-with-one-of-the-strings-from-a-list
#   - Rounding up numbers using the math lib - https://stackoverflow.com/questions/2356501/how-do-you-round-up-a-number-in-python
#   - Logging function was copied and modified by Jan - https://aykutakin.wordpress.com/2013/08/06/logging-to-console-and-file-in-python/
#   - Date and time formatting for logging purposes - https://stackoverflow.com/questions/45446099/python-logging-set-date-as-filename
#   - Since os.path.relpath() does not work on Mac OS, I needed to manually compare the paths - https://stackoverflow.com/questions/30683463/comparing-two-strings-and-returning-the-difference-python-3
#   - Emailing attachments - https://stackoverflow.com/questions/25346001/add-excel-file-attachment-when-sending-python-email
#   - Verify free disk space - https://stackoverflow.com/questions/4260116/find-size-and-free-space-of-the-filesystem-containing-a-given-file
#   - Process name check - https://stackoverflow.com/questions/2940858/kill-process-by-name

# ===== DO NOT MODIFY BEYOND THIS POINT UNLESS YOU ARE EXPERIENCED ===

# The max zip file size MUST be smaller than the max file size, as otherwise it would result in the zipping of the chunks
# and a never ending cycle that would fill up the entire partition.
max_zip_size = max_single_file_size / 100 * 80 # Shown in bytes. Defined as 80% of the max file size.

# All the required libraries - they are all bundled up with a fresh installation of Python 3.x
try:
    import os
    import sys
    from zipfile import ZipFile
    import fnmatch
    import math
    import traceback
    import logging
    import subprocess
    from datetime import datetime
    from sys import platform as _platform
    import smtplib
    import mimetypes
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders
except:
    print("A required Python 3.x library could not be loaded.\nSee below for more details.\nProgram is terminating.\n")
    traceback.print_exc(limit=2, file=sys.stderr)

# These can only be defined after the libraries since a lib is being used for this.
logfile_all = datetime.now().strftime('rclone_debug_%Y-%m-%d-%H_%M_%S.log')
logfile_errors = datetime.now().strftime('rclone_errors_%Y-%m-%d-%H_%M_%S.log')

# Check if folders defined by admin exist and exit if not:
if not os.path.exists(root_dir):
    print("\nERROR! The user-defined source folder (what to backup) in " + root_dir + " does not exist! \nCannot continue. Edit the script to make sure the path is correct.")
    sys.exit()

if not os.path.exists(log_folder):
    print("\nERROR! The user-defined log folder in " + log_folder + " does not exist! \nCannot continue. Edit the script to make sure the path is correct.")
    sys.exit()

if not os.path.exists(rclone_program_location):
    print("\nERROR! The user-defined rclone application location in " + rclone_program_location + " does not exist! \nCannot continue. Edit the script to make sure the path is correct.")
    sys.exit()


def rclone_logger():

	# Required libraries - logging & os.path
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to info
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # create error file handler and set level to error
    handler = logging.FileHandler(os.path.join(log_folder, logfile_errors),"w", encoding=None, delay="true")
    handler.setLevel(logging.ERROR)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # create debug file handler and set level to debug
    handler = logging.FileHandler(os.path.join(log_folder, logfile_all),"w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    #Usage:
	#logging.debug("debug message")
	#logging.info("info message")
	#logging.warning("warning message")
	#logging.error("error message")
	#logging.critical("critical message")

# Call the logger function (this will also test whether logging works)
try:
	rclone_logger()
except:
	# Using print here because the logger is not working in this case.
    print ("\nERROR! Failed to load a logging function, which is required for messages to console and log files to work.\nMake sure that the following files are write-able:" + logfile_all + "and" + logfile_errors + ".\nSee below for more details.\nProgram is terminating.\n")
    traceback.print_exc(limit=2, file=sys.stderr)
    sys.exit()

script_starttime = datetime.now().strftime('%Y-%m-%H at %H:%I:%M')
logging.info("rClone chunking script")
logging.info("======================")
logging.info("Script was initiated on " + script_starttime + ".")
logging.info("Max single file size defined as " + str(max_single_file_size / 1000000) + " MB.")
logging.info("")
logging.info("Source folder: " + root_dir)
logging.info("Destination folder: " + rclone_dest_folder)
logging.info("Destination service type: " + rclone_service_name)
logging.info("Log folder: " + log_folder)
logging.debug("Log file (catch-all): " + logfile_all)
logging.debug("Log file (errors-only): " + logfile_errors)
#logging.info("")
logging.debug("Rclone app folder: " + rclone_program_location)
logging.debug("Extensions to skip: " + str(extensions_to_skip))
logging.debug("Buffer size for zipping: " + str(buf_size/1000000) + "MBs.")

# Check if the process is already running and if yes, then skip or kill
processname = os.path.basename(__file__)
tmp = os.popen("ps -Af").read()
proccount = tmp.count(processname)

if proccount > 0:

		if (what_if_already_running == 1):
			logging.info("Script is terminating because it is already running and the user-defined value 'what_if_already_running' is set to not proceed.")
			sys.exit()
	
		if (what_if_already_running == 2):
			logging.info("The same script is already running. The 'what_if_already_running' variable is set to kill the previous process. Attempting to kill the previous process...")
			try:
				os.system('pkill '+ processname)
			except:
				logging.error("Could not stop the previously running script. Terminating...")
				sys.exit()
	

def check_disk_space():
    try:
        logging.info("- Checking if there is enough space on the local drive before the process starts.")
        disk = os.statvfs(currentpath)
        free_percent = 100 - (disk.f_blocks - disk.f_bfree) * 100 / (disk.f_blocks -disk.f_bfree + disk.f_bavail) + 1


        if math.ceil(free_percent) < 10:
            critical_failure_text = "There is not enough space on the local drive to continue the zipping process."
            critical_failure(critical_failure_text)
        else:
            logging.info("-- The local drive has " + str(math.ceil(free_percent)) + "% of space. The script can therefore proceed safely.")

    except:
        logging.warning("- Unable to check free space on the local drive. The program will continue.")


def zipfiles():

    # Verify that there is at least 10% of space on the local drive.
    check_disk_space()

    logging.info("- Zipping " + file + " as " + outputZIP)

    # Do NOT enable compression as this would lead to a miss-match when comparing file size of individual chunks with the large file and so new chunking and uploads at every cycle.
    try:
        # If the .rclone folder does not exists, yet, then create it, since chunks will be saved there.
        if not os.path.exists(rclone_folder_with_chunks):
            os.makedirs(rclone_folder_with_chunks)

        # Zips an individual file without compression (as large videos do not benefit).
        with ZipFile (outputZIP, 'w') as myzip:
            myzip.write(path_and_file, arcname=None, compress_type=None)
        logging.info("-- File " + file + " was zipped as " + outputZIP + " successfully!")
    except:
        critical_failure_text = "Zipping of the file " + file + " failed!"
        critical_failure(critical_failure_text)

# A class that is called when a large file needs to be splitted into chunks
# This code was copied directly from https://stackoverflow.com/questions/22751000/split-large-text-filearound-50gb-into-multiple-files/22752317 .
class FileSpliter:
    # If file type is text then CHUNK_SIZE is count of chars
    # If file type is binary then CHUNK_SIZE is count of bytes - default 1GB
    def __init__(self, InputFile, FileType="b", CHUNK_SIZE=1047483648):
        self.CHUNK_SIZE = CHUNK_SIZE    # byte or char
        self.InputFile = InputFile
        self.FileType = FileType        # b: binary,  t: text
        self.OutFile = InputFile+".00"
        self.FileSize = 0
        self.Parts = None
        self.CurrentPartNo = 1
        self.Progress = 0.0

    def Prepare(self):
        #if not(os.path.isfile(self.InputFile) and os.path.getsize(self.InputFile) > 0):
        #    print("ERROR: The file is not exists or empty!")
        #    return False
        self.FileSize = os.path.getsize(self.InputFile)
        if self.CHUNK_SIZE >= self.FileSize:
            self.Parts = 1
        else:
            self.Parts = math.ceil(self.FileSize / self.CHUNK_SIZE)
        return True

    def Split(self):
        if self.FileSize == 0 or self.Parts == None:
            print("ERROR: File is not prepared for split!")
            return False
        with open(self.InputFile, "r" + self.FileType) as f:
            while True:
                if self.FileType == "b":
                    buf = bytearray(f.read(self.CHUNK_SIZE))
                elif self.FileType == "t":
                    buf = f.read(self.CHUNK_SIZE)
                else:
                    print("ERROR: File type error!")
                if not buf:
                    # we've read the entire file in, so we're done.
                    break
                of = self.OutFile + str(self.CurrentPartNo)
                outFile = open(of, "w" + self.FileType)
                outFile.write(buf)
                outFile.close()
                self.CurrentPartNo += 1
                self.ProgressBar()
        return True

    def Rebuild(self):
        self.CurrentPartNo = 0
        if self.Parts == None:
            return False
        with open(self.OutFile, "w" + self.FileType) as f:
            while self.CurrentPartNo < self.Parts:
                If = self.OutFile + str(self.CurrentPartNo)
                if not(os.path.isfile(If) and os.path.getsize(If) > 0):
                    logging.error("ERROR: The file [" + If + "] does not exists or is empty!")
                    return False
                InputFile = open(If, "r" + self.FileType)
                buf = InputFile.read()
                if not buf:
                    # we've read the entire file in, so we're done.
                    break
                f.write(buf)
                InputFile.close()
                os.remove(If)
                self.CurrentPartNo += 1
                self.ProgressBar()
        return True

    def ProgressBar(self, BarLength=20, ProgressIcon="#", BarIcon="-"):
        # You can't have a progress bar with zero or negative length.
        if BarLength <1:
            BarLength = 20
        # Use status variable for going to the next line after progress completion.
        Status = ""
        # Calcuting progress between 0 and 1 for percentage.
        self.Progress = float(self.CurrentPartNo) / float(self.Parts)
        # Doing this conditions at final progressing.
        if self.Progress >= 1.:
            self.Progress = 1
            Status = "\r\n"    # Going to the next line
        # Calculating how many places should be filled
        Block = int(round(BarLength * self.Progress))
        # Show this
        Bar = "\r[{}] {:.0f}% {}".format(ProgressIcon * Block + BarIcon * (BarLength - Block), round(self.Progress * 100, 0), Status)
        print(Bar, end="")


def chunk_zip_file():
    # Splits file into pieces as per max_zip_size definition above.
    # This function was directly copied from source listed in the top of the script.

    # Verify that there is at least 10% of space on the local drive.
    check_disk_space()

    try:
        # In case the .rclone folder was not yet created then create it.
        if not os.path.exists(rclone_folder_with_chunks):
            os.makedirs(rclone_folder_with_chunks)

        fp = FileSpliter(InputFile=outputZIP, FileType="b", CHUNK_SIZE=max_single_file_size)
        if fp.Prepare():
            # Spliting ...
            logging.info("- Splitting " + outputZIP + " into chunks.")
            sr = fp.Split()
            if sr == True:
                logging.info("-- The file splited successfully.")
    except:
        critical_failure_text="Chunking of the file " + file + " failed!"
        critical_failure(critical_failure_text)


def determine_dest_path_on_remote_service():
    #  Reset the destination path. Its value comes from the comp. of the current_dir & root_dir
    #global dest_path
    dest_path2 = ""

    # In case the OS is MaxOS then os.realpath() does not work.
    # In such a case a manual comparison of the strings is done.
    if (_platform == "darwin"):
        #logging.info("-- Determining the path on " + rclone_service_name + " based on " + currentpath + " on Mac OS.")
        maxlen=len(currentpath)
        for i in range(maxlen):
            letter1=root_dir[i:i+1]
            letter2=currentpath[i:i+1]

            if letter1 != letter2:
                dest_path2+=letter2

            # After the two paths are compared, the longer one always starts with / , which needs to be removed.
            if dest_path2.startswith("/"):
                dest_path2 = dest_path2[-1]

    # Use os.path.relpath on all other platforms, since this is safer.
    else:
        dest_path2 = os.path.relpath(currentpath, root_dir)

    #logging.info("--- dest_path was determined to be: " + dest_path2 + ".")
    return(dest_path2)

def rclone_file():

    try:
        dest_path = determine_dest_path_on_remote_service()

        # In case the folder to which the file is copied is the root folder of the final location, then do not create a folder with the name of a dot.
        if (dest_path == "."):
            dest_path = ""

        if (rcloning_chunks == 1):
            logging.info("-- Rcloning chunk " + file_to_rclone + " to " + os.path.join(rclone_dest_folder, dest_path) + ".")
            path_and_file_to_rclone = os.path.join(rclone_folder_with_chunks, file_to_rclone)
        else:
            logging.info("-- Rcloning file " + file + " to " + os.path.join(rclone_dest_folder, dest_path) + ".")
            path_and_file_to_rclone = os.path.join(currentpath, file_to_rclone)

        # I used these two lines when debugging (can be removed):
        #logging.info("--- " + rclone_program_location + "rclone copy '" + path_and_file_to_rclone + "' " + rclone_service_name + ":'" + os.path.join(rclone_dest_folder, dest_path) + "'")
        #os.system(rclone_program_location + 'rclone copy "' + path_and_file_to_rclone + '" ' + rclone_service_name + ':"' + os.path.join(rclone_dest_folder, dest_path) + '"')

        # As for the part where rclone_program_location is joined with '', it adds the trailing slash for the folder.
        rclone_copy_subprocess = subprocess.Popen([os.path.join(rclone_program_location,'') +'rclone copy -vv "' + u'{}'.format(path_and_file_to_rclone) + '" ' + rclone_service_name + ':"' + os.path.join(rclone_dest_folder, dest_path) + '"'], shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if rclone_copy_subprocess.wait() != 0:
            logging.error("--- Errors found during the rcloning of " + file_to_rclone + " to " + rclone_service_name + ":" + os.path.join(rclone_dest_folder, dest_path) + " .")
            for line in rclone_copy_subprocess.stderr:
                logging.error("---- " + line)
        else:
            # xxx These two lines are just for troublehshooting
            #for line in rclone_copy_subprocess.stderr:
            #    logging.debug("---- " + line)
            logging.info("--- Upload (or CRC check with " + rclone_service_name + ") was successfully finished.")

    except KeyboardInterrupt:
        logging.info("\nThe script was terminated by the admin. No logs will be emailed.")
        sys.exit()
    except:
        critical_failure_text="Failed to rclone " + file + " to the " + rclone_service_name + " service."
        critical_failure(critical_failure_text)

def critical_failure(critical_failure_text):
    logging.error("")
    logging.error("======================================")
    logging.error("CRITICAL ERROR ENCOUTERED - see below:")
    logging.error("======================================")

    if os.path.isfile(path_and_file):
        logging.error("Last path and file processed: " + path_and_file)

    if critical_failure_text.strip():
        logging.error("REASON: " + critical_failure_text)

    logging.error("Further details: " , exc_info=2)
    logging.error("")

    # Email logs out
    logging.error("Attempting to email out / upload log files.")
    try:
        mail_logs()
    except:
        logging.error("ERROR! Emailing log files failed!")

    # If saving of logs to destination is allowed, then try to upload the logs.
    if upload_logs_to_dest == "yes" or upload_logs_to_dest == "Yes" or upload_logs_to_dest == "YES":
        try:
            upload_logs()
        except:
            logging.error("ERROR! Uploading of log files to " + rclone_service_name + " failed!")

    logging.error("")
    logging.error("rClone chunking script is terminating.")
    sys.exit()

def scan_for_chunks():
    # Identify all chunks from the large file to later check for their amount and size
    global file_chunks # These 3 global variables are used in main body
    global sum_chunk_size  # + they are used in the verify_chunk_integrity function.
    global chunk_number
    sum_chunk_size = 0
    chunk_number = 0
    file_chunks = [] # This variable is an array - multiple chunks are expected. It is used in the verify function too
    try:
        for candidate_for_chunk in os.listdir(rclone_folder_with_chunks):
            #logging.info("-- Scanning " + candidate_for_chunk + " in " + rclone_folder_with_chunks)

            # If the file name matches with the scanned file in the folder (in case the file was already in .zip format then the second clause apply)
            if fnmatch.fnmatch(candidate_for_chunk, file + "*.zip.*") or fnmatch.fnmatch(candidate_for_chunk, file + ".*"):
                #logging.info("--- Match with " + candidate_for_chunk + " was found.")
                file_chunks.append(candidate_for_chunk)
                candidate_chunk_size = os.stat(os.path.join(rclone_folder_with_chunks, candidate_for_chunk)).st_size
                chunk_number += 1
                # Add the size of the chunk so that we can compare it with what it should be
                sum_chunk_size = sum_chunk_size + candidate_chunk_size
        logging.info("-- All the chunks found: " + str(file_chunks))
    except:
        critical_failure_text="Scanning for chunks for file " + file + "failed!"
        critical_failure(critical_failure_text)

    return sum_chunk_size

def verify_chunk_integrity():
    # Three tests are ran to verify the chunk integrity.
    logging.info("- Verifying archive integrity on source.")
    global file_already_chunked_verified
    global chunks_to_skip
    # For each folder, reset the file list to skip in case there are chunks that fail verification.
    chunks_to_skip = []

    try:
        # TEST No.1
        logging.info("-- Test no.1 - does amount of chunks correspond with current chunk size settings?")
        # Divide the file size by the max chunk size and round it up to find out how many chunks should there be.
        no_files_to_be_chunked = math.ceil(file_size / max_zip_size)

        if chunk_number != no_files_to_be_chunked:
            logging.warning("--- WARNING! Based on current settings, the number of chunks should be " + str(no_files_to_be_chunked) + " instead of " + str(chunk_number) + "!")
        else:
            logging.info("--- Passed - number of file chunks matches the current settings.")
            file_already_chunked_verified += 1

        # TEST No.2
        logging.info("-- Test no.2 - Does the size of the chunks match the size of " + file + "?")

        # Sum up the size of the chunks versus the file.
        if sum_chunk_size != file_size:
            logging.warning("--- WARNING! Chunk size of " + str(sum_chunk_size/1000000) + " MB does not match the original file size of " + str(file_size/1000000) + " MB! Possible archive corruption detected.")
        else:
            logging.info("--- Passed - sum of chunk size matches with the large file (" + str(sum_chunk_size/1000000) + " MB).")
            file_already_chunked_verified += 1

        # TEST No.3 - Check if max chunk file size has changed.
        logging.info("-- Test no.3 - is the size of th first chunk size equal to 80% of the max chunk file size?")
        #logging.info("Checking if size of the first chunk called " + str(file_chunks[0]) + "(size " + str(os.path.getsize(os.path.join(rclone_program_location, file_chunks[0]))) + " bytes) equals to the pre-defined max chunk size, which is " + str(max_zip_size) + " bytes.")

        # When the chunking function does the chunking, it may not split it exactly by byte. This variable compares it and then allows for a 1 byte difference.
        compare_max_chunk_size_with_existing_chunk = os.path.getsize(os.path.join(rclone_folder_with_chunks, file_chunks[0])) - max_zip_size
        logging.debug("--- The size difference is " + str(compare_max_chunk_size_with_existing_chunk) + " byte(s). At most -1 or +1 byte difference is tolerated.")

        if (compare_max_chunk_size_with_existing_chunk > 1 or compare_max_chunk_size_with_existing_chunk < -1):
    #    if (os.path.getsize(os.path.join(rclone_program_location, file_chunks[0])) != max_zip_size):
            logging.warning("--- WARNING! Max chunk size of " + str(max_zip_size) + " bytes as defined in this script does not equal the size of the first chunk of this file, which is " + str(os.path.getsize(os.path.join(rclone_folder_with_chunks, file_chunks[0]))) + " bytes. The chunks will need to be re-created.")
        else:
            logging.info("--- Passed - max chunk size has not changed since the script was ran last time.")
            file_already_chunked_verified += 1

        # In case one of the three tests did not pass, then remove the chunks.
        # The chunks will be re-created later in case the file is still considered too large.
        if ( file_already_chunked_verified < 3 ):
            logging.info("-- Chunk verification on source FAILED. Flushing away the chunks since one or more integrity tests failed.")
            for chunk_to_delete in file_chunks:
                path_to_chunk_to_delete = os.path.join(rclone_folder_with_chunks, chunk_to_delete)
                logging.info("--- Removing " + chunk_to_delete + " from the source.")
                os.remove(path_to_chunk_to_delete)
                logging.info("--- Removing " + chunk_to_delete + " from the destination.")
                # Call the function to determine path on destination. This is needed for Mac OS X since it cannot do os.path.relpath()
                dest_path = determine_dest_path_on_remote_service()
                # Attempt to delete the chunks
                try:
                    #logging.info("----" + rclone_program_location + " rclone deletefile " + rclone_service_name + ":'" + os.path.join(rclone_dest_folder, dest_path, chunk_to_delete) + "'")

                    os.system(os.path.join(rclone_program_location,'') + 'rclone deletefile ' + rclone_service_name + ':"' + os.path.join(rclone_dest_folder, dest_path, chunk_to_delete) + '"')
                except:
                    logging.error("--- FAILED to remove the chunk from the destination.")
                # Add the file into the tuple (the comma is on purpose to indicate the end of the record)
                chunks_to_skip += (chunk_to_delete,)
            logging.info("--- Chunks added to the exception list: " + str(chunks_to_skip))
        else:
            logging.info("--- Chunk verification on source PASSED.")
            logging.info("-- Verifying chunks in destination.")

    except:
        critical_failure_text="The process of verifying chunks' integrity encoutered errors."
        critical_failure(critical_failure_text)

def upload_logs():

    logfile_year = datetime.now().strftime('%Y')
    logfile_month = datetime.now().strftime('%m')

    log1_copy_subprocess = subprocess.Popen([os.path.join(rclone_program_location,'') +'rclone copy -vv "' + os.path.join(log_folder, logfile_all) + '" ' + rclone_service_name + ':"' + os.path.join(dest_logs_path, logfile_year, logfile_month) + '"'], shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Rclone also the error log file if it exists
    if os.path.isfile(os.path.join(log_folder,logfile_errors)):
        log2_copy_subprocess = subprocess.Popen([os.path.join(rclone_program_location,'') +'rclone copy -vv "' + os.path.join(log_folder, logfile_errors) + '" ' + rclone_service_name + ':"' + os.path.join(dest_logs_path, logfile_year, logfile_month) + '"'], shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if log1_copy_subprocess.wait() != 0:
        logging.error("- Errors found during the rcloning of logs to " + rclone_service_name + ":" + int(os.path.join(dest_logs_path, logfile_year, logfile_month)) + " .")
        # It is excpted that the error will be the same for both logs, so only one upload's error output is being displayed.
        for line in log1_copy_subprocess.stderr:
            logging.error("--   " + line)

    else:
            logging.info ("- The upload of logs to " + rclone_service_name + " was successfully finished.")

def mail_logs():

    try:
        # If the error log file does not exist, then do not add it to the list of attachments
        if os.path.isfile(os.path.join(log_folder,logfile_errors)):
            email_attachments=[os.path.join(log_folder, logfile_all),os.path.join(log_folder, logfile_errors)]
        else:
            email_attachments=[os.path.join(log_folder, logfile_all)]

        # Define the header and the body of the multipart message
        msg = MIMEMultipart()
        msg['From'] = email_from
        msg['To'] = ", ".join(email_to)
        msg['Subject'] = email_subject

        # Attach the email text defined by the admin at the top of this script
        msg.attach(MIMEText(email_text))

        # Open each log file and add it as an attachment.
        for a_file in email_attachments:
            attachment = open(a_file, 'rb')
            file_name = os.path.basename(a_file)
            part = MIMEBase('application','octet-stream')
            part.set_payload(attachment.read())
            part.add_header('Content-Disposition','attachment', filename=file_name)
            #encoders.encode_base
            msg.attach(part)

        mailServer = smtplib.SMTP("smtp.gmail.com", 587)
        mailServer.ehlo()
        mailServer.starttls()
        mailServer.ehlo()
        mailServer.login(email_from, email_from_pwd)
        mailServer.sendmail(email_from, email_to, msg.as_string())
        # Should be mailServer.quit(), but that crashes...
        mailServer.quit()
        logging.info ("- The logs were successfully emailed out.")
    except:
        critical_failure_text="Could not email out the log files!"
        critical_failure()

def graceful_finish():
    logging.info("")

    script_endtime = datetime.now().strftime('%Y-%m-%H at %H:%I:%M')

    logging.info("Rcloning files to destination has finished on " + script_endtime + ".")
    logging.info("")

    logging.info("No. of files checked/rcloned: " + str(files_count))
    logging.info("No. of files chunks checked/rcloned: " + str(files_chunk_count))
    logging.info("No. of folders checked/rcloned: " + str(folders_count))
    logging.info("Total size of files checked/rcloned: " + str(math.ceil(sum_size_count)) + " MB")

    logging.info("")

    if os.path.isfile(os.path.join(log_folder,logfile_errors)):
        logging.info("Errors were detected when running the script. For this reason the log file will be emailed.")
        logging.info("----- END OF LOG FILE ------")
        mail_logs()
    else:
        logging.info("No errors were encoutered when running this script (thus no log file will be emailed.")
        logging.info("----- END OF LOG FILE ------")

        if upload_logs_to_dest.lower() == "yes":
            upload_logs()

    sys.exit()


## ==== ##
## MAIN ##
## ==== ##

# Reset the count for stats
files_count = 0 # How many files has the script checked
files_chunk_count = 0 # How many chunks are checked/rcloned
folders_count = 0 # How many files has the script checked
sum_size_count = 0 # Sum of the size of files the script checked
critical_failure_text = ""

# Go through the path defined above as root_dir
for currentpath, folders, files in os.walk(root_dir):
    # In each folder, reset the names of chunks for which verification failed. This is in case there are same file names in different folders.
    chunks_to_skip = []
    folders_count += 1

    # Skip the .rclone folder as chunks in there are checked separately.
    if fnmatch.fnmatch(currentpath, "*/.rclone"):
        #logging.info("The folder .rclone is a special folder be skipped.")
        continue

    # For each file found in each folder, do the following:
    for file in files:

        # If the hour to finish the script has been reached, then finish gracefully.
        #current_hour =
        try:
            if (datetime.now().strftime('%H') >= hour_to_gracefully_finish ):
                logging.info("")
                logging.info("The script is finishing gracefully because it has reached the user-defined time to finish.")
                graceful_finish()
        # In case the variable was not defined (i.e. the script is not to terminate at certain hour), then skip
        except NameError:
            pass

        files_count += 1
        path_and_file = os.path.join(currentpath, file)
        rclone_folder_with_chunks = os.path.join(currentpath, ".rclone") # A sub-folder called .rclone contains the zipped chunked files.
        logging.info("")
        logging.info("Processing file " + file + " in " + currentpath)

        rcloning_chunks = 0 # This value resets with every file and will turn to 1 if a zip file chunks are found to be rcloned.
        file_is_too_large = 0 # Again this value will be 1 is the file is larger than max_single_file_size.
        file_already_chunked_verified = 0 # This will turn to 2 in case a chunk verification passes both tests, which means that the file was previously already chunked and thus does not need to be chunked again.

        # Skip files extensions that are on the ignore list. Special case is .bundles.
        if (file.endswith(tuple(extensions_to_skip))) or (fnmatch.fnmatch(currentpath, "*.bundle/*")) or (file.endswith(tuple(chunks_to_skip))):
            logging.info("- File is skipped as its extension or filename is listed as not to be copied.")

        else:
            # Perform a check that the file on source exists in case something happened to it.
            if not os.path.isfile(path_and_file):
                logging.warning("WARNING! File " + file + " no longer exists. Reason could be that it was created only temporarily during zipping or removed by the user/system in the meantime." )
                continue

            # Determine file size of the file and convert it to MB.
            file_size = os.path.getsize(path_and_file)
            file_size_mb = file_size / 1000000
            sum_size_count += file_size_mb

            logging.info("- Filesize is " + str(round(file_size_mb, 3)) + " MB.")

            # Check if the chunks for this large file already exist. If yes, skip the large file. Individual chunks will be verified with the cycle later.

            logging.debug("- Checking if the file was previously chunked (if file " + os.path.join(rclone_folder_with_chunks, file) + ".zip.001 -OR- " + os.path.join(rclone_folder_with_chunks, file) + ".001 exists.")

            if os.path.isfile(os.path.join(rclone_folder_with_chunks, file) + ".001" or os.path.isfile(os.path.join(rclone_folder_with_chunks, file) + ".zip.001")):

                logging.info("- File was previously chunked. Gathering all the chunks on source to compare them with destination.")

                # Identify all chunks from the large file to later check for their amount and size
                scan_for_chunks()

                # Confirm that the chunks previously created (on source) are as large as defined in the max_zip_size variable. If it was changed then the chunks will be re-created.
                verify_chunk_integrity()

            # Check file size. If > max_single_file_size AND if chunk verification has not passed (3 different tests and for each pass the value is +1), then zip it, chunk it and rclone it.
            if file_size > max_single_file_size :

                # If the file has not been chunked before OR if the verification of the chunks failed, then created them again.
                if file_already_chunked_verified < 3:
                    logging.info("- File is larger than " + str(round(max_single_file_size / 1000000)) + " MB and thus cannot be uploaded as-is.")
                    file_is_too_large = 1

                    # In case the file is already in the .zip format, then there is no need to zip it again and thus zipping is skipped.
                    if not file.endswith('.zip'):
                        logging.info("- Zipping and chunking " + file)
                        outputZIP = os.path.join(rclone_folder_with_chunks, file) + '.zip'
                        zipfiles()

                        # Chunk the zip file
                        chunk_zip_file()

                        # Need to error proof the line below:
                        logging.info("- Removing temporary file " + outputZIP)
                        os.remove(outputZIP)
                    else:
                        logging.info("- File is already in the .zip format and thus will not be zipped again.")
                        outputZIP = path_and_file

                        # Chunk the zip file
                        chunk_zip_file()

                    # Identify names of chunks that have been created
                    logging.info("- Scanning for chunks to upload.")
                    scan_for_chunks()

                logging.info("- Rcloning chunks to destination.")
                rcloning_chunks = 1
                for file_chunk in file_chunks:
                    file_to_rclone = file_chunk
                    files_chunk_count += 1
                    rclone_file()

            elif ( file_size < max_single_file_size ):
                # If file size is not larger than the specified amount, then attempt to rclone it to destination, which will perform CRC checks, etc.
                file_to_rclone = file
                rclone_file()

graceful_finish()
