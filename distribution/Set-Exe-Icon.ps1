[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$Exe,
    [Parameter(Mandatory=$true)] [string]$Icon
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 includes the C# compiler used by Add-Type. No SDK,
# external executable, online service, or additional tool download is required.
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
public static class DKIconResources {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr BeginUpdateResource(string fileName, bool deleteExistingResources);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool UpdateResource(IntPtr handle, IntPtr type, IntPtr name, ushort language, byte[] data, uint length);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool EndUpdateResource(IntPtr handle, bool discard);
    static void Write(IntPtr handle, int type, int id, byte[] data) {
        if (!UpdateResource(handle,(IntPtr)type,(IntPtr)id,0,data,(uint)data.Length))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public static void Apply(string executable, string icon) {
        byte[] ico=File.ReadAllBytes(icon);
        using (MemoryStream src=new MemoryStream(ico))
        using (BinaryReader reader=new BinaryReader(src)) {
            if(reader.ReadUInt16()!=0||reader.ReadUInt16()!=1)
                throw new InvalidDataException("Not a Windows ICO file");
            int count=reader.ReadUInt16();
            if(count<1||count>64)throw new InvalidDataException("Unsupported icon count");
            byte[][] images=new byte[count][];
            byte[][] groups=new byte[count][];
            HashSet<int> sizes = new HashSet<int>();
            for(int i=0;i<count;i++){
                byte[] group=reader.ReadBytes(12);
                if(group.Length!=12)throw new EndOfStreamException();
                int width=group[0]==0?256:group[0];
                int height=group[1]==0?256:group[1];
                if(width==height)sizes.Add(width);
                uint length=BitConverter.ToUInt32(group,8);
                uint offset=reader.ReadUInt32();
                if(length==0||length>16*1024*1024||offset>ico.Length||length>ico.Length-offset)
                    throw new InvalidDataException("Invalid ICO entry");
                images[i]=new byte[(int)length];
                Buffer.BlockCopy(ico,(int)offset,images[i],0,(int)length);
                groups[i]=group;
            }
            foreach(int required in new int[]{16,32,48,256})
                if(!sizes.Contains(required))
                    throw new InvalidDataException("ICO must include 16, 32, 48 and 256 pixel icons");
            byte[] directory;
            using(MemoryStream mem=new MemoryStream())
            using(BinaryWriter writer=new BinaryWriter(mem)){
                writer.Write((ushort)0);
                writer.Write((ushort)1);
                writer.Write((ushort)count);
                for(int i=0;i<count;i++){
                    writer.Write(groups[i]);
                    writer.Write((ushort)(301+i));
                }
                directory=mem.ToArray();
            }
            IntPtr handle=BeginUpdateResource(executable,false);
            if(handle==IntPtr.Zero)throw new Win32Exception(Marshal.GetLastWin32Error());
            bool commit=false;
            try{
                for(int i=0;i<count;i++)Write(handle,3,301+i,images[i]);
                // Group 1 takes precedence over normal .NET icon group IDs.
                Write(handle,14,1,directory);
                commit=true;
            }finally{
                if(!EndUpdateResource(handle,!commit))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        }
    }
}
'@
$exePath = (Resolve-Path -LiteralPath $Exe -ErrorAction Stop).Path
$iconPath = (Resolve-Path -LiteralPath $Icon -ErrorAction Stop).Path
if ([IO.Path]::GetExtension($exePath) -ine '.exe') { throw 'Expected an EXE file' }
if ([IO.Path]::GetExtension($iconPath) -ine '.ico') { throw 'Expected an ICO file' }
$signature = Get-AuthenticodeSignature -LiteralPath $exePath
if ($null -ne $signature.SignerCertificate) {
    throw 'A signed executable must not be modified. Apply the icon before code signing.'
}
[DKIconResources]::Apply($exePath,$iconPath)
Write-Output 'EXE_ICON_UPDATED'
