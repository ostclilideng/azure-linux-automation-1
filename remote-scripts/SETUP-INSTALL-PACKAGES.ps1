﻿<#-------------Create Deployment Start------------------#>
Import-Module .\TestLibs\RDFELibs.psm1 -Force
$result = ""
$testResult = ""
$SetupStatus= ""
$resultArr = @()

$isDeployed = DeployVMS -setupType $currentTestData.setupType -Distro $Distro -xmlConfig $xmlConfig -getLogsIfFailed $true
if ($isDeployed)
{
    try
    {
        $testServiceData = Get-AzureService -ServiceName $isDeployed

#Get VMs deployed in the service..
        $testVMsinService = $testServiceData | Get-AzureVM

        $hs1vm1 = $testVMsinService
        $hs1vm1Endpoints = $hs1vm1 | Get-AzureEndpoint
        $hs1vm1sshport = GetPort -Endpoints $hs1vm1Endpoints -usage ssh
        $hs1VIP = $hs1vm1Endpoints[0].Vip
        $hs1ServiceUrl = $hs1vm1.DNSName
        $hs1ServiceUrl = $hs1ServiceUrl.Replace("http://","")
        $hs1ServiceUrl = $hs1ServiceUrl.Replace("/","")
        $hs1vm1Hostname =  $hs1vm1.Name

        RemoteCopy -uploadTo $hs1VIP -port $hs1vm1sshport -files $currentTestData.files -username $user -password $password -upload -doNotCompress
        RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "chmod +x *" -runAsSudo

        LogMsg "Executing : $($currentTestData.testScript)"
        try{
            $output = RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "$python_cmd ./$($currentTestData.testScript)" -runAsSudo

			$output = RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "ls /home/$user/SetupStatus.txt  2>&1" -runAsSudo
			
			if($output -imatch "/home/$user/SetupStatus.txt")
			{
				$SetupStatus = RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "cat /home/$user/SetupStatus.txt" -runAsSudo
				$out = RemoteCopy -download -downloadFrom $hs1VIP -files "/home/$user/PackageStatus.txt" -downloadTo $LogDir -port $hs1vm1sshport -username $user -password $password 2>&1 | Out-Null
				$sfile=Get-Content -Path $LogDir\PackageStatus.txt 
				$i=0
				foreach ($line in $sfile)
				{
					if($line -imatch "Started" -or $line -imatch "Completed" -or $line -imatch "successfully")
					{
						LogMsg "$i : $line"
					}
					elseif($line -imatch "failed")
					{
						LogErr "$i : $line"
					}
					$i=$i+1
				}
				if($SetupStatus -imatch "PACKAGE-INSTALL-CONFIG-PASS")
				{
					LogMsg "** All the required packages for the distro installed successfully **"			
					RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "service waagent stop" -runAsSudo -ignoreLinuxExitCode
					RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "rm -rf /var/log/*;sync" -runAsSudo
					#VM De-provision
					$output = RunLinuxCmd -username $user -password $password -ip $hs1VIP -port $hs1vm1sshport -command "waagent -force -deprovision" -runAsSudo
					
					if($output -match "root password will be disabled")
					{
						LogMsg "** VM De-provisioned Successfully **"
						LogMsg "Stopping a VM to prepare OS image : $hs1vm1Hostname"
						$tmp = Stop-AzureVM -ServiceName $isDeployed -Name $hs1vm1Hostname -Force
						LogMsg "VM stopped successful.."
						
						LogMsg "Capturing the OS Image"
						$NewImageName = $isDeployed + '-prepared'
						$tmp = Save-AzureVMImage -ServiceName $isDeployed -Name $hs1vm1Hostname -NewImageName $NewImageName -NewImageLabel $NewImageName
						LogMsg "Successfully captured VM image : $NewImageName"
						
						#Remove the Cloud Service
						LogMsg "Executing: Remove-AzureService -ServiceName $isDeployed -Force"
						Remove-AzureService -ServiceName $isDeployed -Force
						
						# Capture the prepared image names
						$PreparedImageInfoLogPath = "$pwd\PreparedImageInfoLog.xml"
						if((Test-Path $PreparedImageInfoLogPath) -eq $False)
						{
							$PreparedImageInfoLog = New-Object -TypeName xml
							$root = $PreparedImageInfoLog.CreateElement("PreparedImages")
							$content = "<PreparedImageName></PreparedImageName>"
							$root.set_InnerXML($content)
							$PreparedImageInfoLog.AppendChild($root)
							$PreparedImageInfoLog.Save($PreparedImageInfoLogPath)
						}
						[xml]$xml = Get-Content $PreparedImageInfoLogPath
						$xml.PreparedImages.PreparedImageName = $NewImageName
						$xml.Save($PreparedImageInfoLogPath)						
						
						$testResult = "PASS"
						LogMsg "Test result : $testResult"
					}
					else{
						LogMsg "** VM De-provision Failed**"
						$testResult = "FAIL"
						LogMsg "Test result : $testResult"
					}
				}
				else{
					$testResult = "FAIL"
					LogMsg "Test result : $testResult"
					GetVMLogs -DeployedServices $isDeployed
				}
			}
			else{
					$testResult = "FAIL"
					GetVMLogs -DeployedServices $isDeployed
			}
		}
		catch{
			$ErrorMessage =  $_.Exception.Message
			LogMsg "EXCEPTION : $ErrorMessage"
			$testResult = "FAIL"
			GetVMLogs -DeployedServices $isDeployed
		}
    }
    catch
    {
        $ErrorMessage =  $_.Exception.Message
        LogMsg "EXCEPTION : $ErrorMessage"   
    }
    Finally
    {
        $metaData = ""
        if (!$testResult)
        {
            $testResult = "Aborted"
        }
        $resultArr += $testResult 
    }
}
else
{
    $testResult = "Aborted"
    $resultArr += $testResult
}

$result = GetFinalResultHeader -resultarr $resultArr

#Clean up the setup
#DoTestCleanUp -result $result -testName $currentTestData.testName -deployedServices $isDeployed

#Return the result and summery to the test suite script..
return $result