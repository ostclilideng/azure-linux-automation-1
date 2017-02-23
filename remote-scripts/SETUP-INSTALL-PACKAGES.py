#!/usr/bin/python
from azuremodules import *
import sys
import shutil
import time
import re
import os
import linecache
import imp
import os.path
import zipfile

current_distro        = "unknown"
distro_version        = "unknown"
sudo_password        = ""
startup_file = ""

rpm_links = {}
tar_link = {}
current_distro = "FreeBSD"
packages_list_xml = "./packages.xml"
python_cmd="python"
waagent_cmd="waagent"
waagent_bin_path="/usr/sbin"


def easy_install(package):
        RunLog.info("Installing Package: " + package+" via easy_install")
        temp = Run("command -v easy_install")
        if not ("easy_install" in temp):
            install_ez_setup()
        if package == "python-crypto":
            output = Run("easy_install pycrypto")
            return ("Finished" in output)
        if package == "python-paramiko":
            output = Run("easy_install paramiko")
            return ("Finished" in output)
        RunLog.error("Installing Package: " + package+" via easy_install failed!!")
        return False


def install_ez_setup():
        RunLog.info ("Installing ez_setup.py...")

        ez_setup = os.path.join("/tmp", "ez_setup.py")
        DownloadUrl(tar_link.get("ez_setup.py"), "/tmp/", output_file=ez_setup)
        if not os.path.isfile(ez_setup):
                RunLog.error("Installing ez_setup.py...[failed]")
                RunLog.error("File not found: {0}".format(ez_setup))
                return False


        output = Run("{0} {1}".format(python_cmd, ez_setup))
        return ("Finished" in output)

def install_waagent_from_github():
        RunLog.info ("Installing waagent from github...")

        pkgPath = os.path.join("/tmp", "agent.zip")
        DownloadUrl(tar_link.get("waagent"), "/tmp/", output_file=pkgPath)
        if not os.path.isfile(pkgPath):
                RunLog.error("Installing waagent from github...[failed]")
                RunLog.error("File not found: {0}".format(pkgPath))
                return False
        
        unzipPath = os.path.join("/tmp", "agent")
        if os.path.isdir(unzipPath):
            shutil.rmtree(unzipPath)

        try:
                zipfile.ZipFile(pkgPath).extractall(unzipPath)
        except IOError as e:
                RunLog.error("Installing waagent from github...[failed]")
                RunLog.error("{0}".format(e))
                return False
        
        waagentSrc = os.listdir(unzipPath)[0]
        waagentSrc = os.path.join(unzipPath, waagentSrc)
        binPath20 = os.path.join(waagentSrc, "waagent")
        binPath21 = os.path.join(waagentSrc, "bin/waagent")
        if os.path.isfile(binPath20):
                #For 2.0, only one file(waagent) needs to be replaced.
                os.chmod(binPath20, 0o755)
                ExecMultiCmdsLocalSudo([
                        "cp {0} {1}".format(binPath20, waagent_bin_path)])
                return True                
        elif os.path.isfile(binPath21):
                #For 2.1, use setup.py to install/uninstall package
                os.chmod(binPath21, 0o755)
                setup_py = os.path.join(waagentSrc, 'setup.py')
                ExecMultiCmdsLocalSudo([
                        "{0} {1} install --register-service --force".format(python_cmd, setup_py)])
                Run('chmod +x /etc/rc.d/waagent')
                return True                
        else:
                RunLog.error("Installing waagent from github...[failed]")
                RunLog.error("Unknown waagent verions")
                return False

def install_package(package):
        RunLog.info ("\nInstall_package: "+package)
        if (package == "waagent"):
                return install_waagent_from_github()
        if (package == "ez_setup"):
                return install_ez_setup()
        else:
                if (current_distro == "FreeBSD"):
                        return PkgPackageInstall(package)
                else:
                        RunLog.error (package + ": package installation failed!")
                        RunLog.info (current_distro + ": Unrecognised Distribution OS found!")
                        return False

def ConfigFilesUpdate():
        update_configuration = False
        RunLog.info("Updating configuration files..")

        # Create a link for bash
        Run("ln -sf /usr/local/bin/bash /bin/bash")

        #Enable boot verbose
        loaderconf = Run("cat /boot/loader.conf")

        if not ('boot_verbose="YES"' in loaderconf):
                Run("echo 'boot_verbose=\"YES\"' >> /boot/loader.conf")  
        
        #Add a user for analysis
        Run("pw useradd -n fortest -s /bin/csh -m")
        Run("echo \"User@123\" | pw mod user fortest -h 0")

        #Configuration of sudoers
        Run("sed -i .bak 's/^[#| ]*ALL ALL=/ALL ALL=/g' /usr/local/etc/sudoers")

        loaderconf = Run("cat /boot/loader.conf")

        if 'boot_verbose="YES"' in loaderconf:
                RunLog.info("/etc/security/pam_env.conf updated successfully\n")
                Run("echo '** Config files are updated successfully **' >> PackageStatus.txt")
                update_configuration = True
        else:
                RunLog.error('Config file not updated\n')
                Run("echo '** updating of config file is failed **' >> PackageStatus.txt")

        if (update_configuration == True):
                RunLog.info('Config file updation succesfully!\n')
                return True
                
        else:
                RunLog.error('[Error] Config file updation failed!')
                return False
                

# Check command or python module is exist on system
def CheckCmdPyModExist(it):
        ret = True
        if(it.lower().startswith('python')):
                try:
                        pymod_name = it[it.index('-')+1:]
                        if(pymod_name == 'crypto'):
                                pymod_name = 'Crypto'
                        imp.find_module(pymod_name)
                except ImportError:
                        ret = False
                        RunLog.error("requisite python module: "+it+" is not exists on system.")
        else:
                output = Run('command -v '+it)
                if(output.find(it) == -1):
                        ret = False
                        RunLog.error("requisite command: "+it+" is not exists on system.")
        return ret

def RunTest():
        UpdateState("TestRunning")
        Run('env ASSUME_ALWAYS_YES=YES pkg bootstrap')
        Run('pkg update')
        success = True
        try:
                import xml.etree.cElementTree as ET
        except ImportError:
                import xml.etree.ElementTree as ET

        #Parse the packages.xml file into memory
        packages_xml_file = ET.parse(packages_list_xml)
        xml_root = packages_xml_file.getroot()

        parse_success = False
        Run("echo '** Installing Packages for '"+current_distro+"' Started.. **' > PackageStatus.txt")
        for branch in xml_root:
                for node in branch:
                        if (node.tag == "packages"):
                                # Get the requisite package list from 'universal' node, that's must have on system
                                if(node.attrib['distro'] == 'universal'):
                                        required_packages_list = node.text.split(',')
                                elif(current_distro == node.attrib["distro"]):
                                        packages_list = node.text.split(",")
                        elif node.tag == "waLinuxAgent_link":
                                tar_link[node.attrib["name"]] = node.text
                        elif node.tag == "ez_setup_link":
                                tar_link[node.attrib["name"]] = node.text
        
        for package in packages_list:
                if(not install_package(package)):
                        # Check if the requisite package is exist already when failed this time
                        if(package in required_packages_list):
                                if(not CheckCmdPyModExist(package)):
                                        success = False
                                        Run("echo '"+package+"' failed to install >> PackageStatus.txt")
                        else:
                                # failure can be ignored
                                Run("echo '"+package+"' failed to install but can be ignored for tests >> PackageStatus.txt")
                        #break
                else:
                        Run("echo '"+package+"' installed successfully >> PackageStatus.txt")

        Run("echo '** Packages Installation Completed **' >> PackageStatus.txt")                
        if success == True:
                if ConfigFilesUpdate():
                        RunLog.info('PACKAGE-INSTALL-CONFIG-PASS')
                        Run("echo 'PACKAGE-INSTALL-CONFIG-PASS' >> SetupStatus.txt")
                else:
                        RunLog.info('PACKAGE-INSTALL-CONFIG-FAIL')
                        Run("echo 'PACKAGE-INSTALL-CONFIG-FAIL' >> SetupStatus.txt")
        else:
                RunLog.info('PACKAGE-INSTALL-CONFIG-FAIL')
                Run("echo 'PACKAGE-INSTALL-CONFIG-FAIL' >> SetupStatus.txt")
        
if not IsFreeBSD():
        RunLog.info("The distro is not FreeBSD\n")
        exit ()
        
#Code execution starts from here
if not os.path.isfile("packages.xml"):
        RunLog.info("'packages.xml' file is missing\n")
        exit ()


RunTest()

