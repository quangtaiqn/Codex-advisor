# Read-only NTFS identity evidence. Paths and alias names never leave this process.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$env:PSModulePath = [IO.Path]::Combine($PSHOME, 'Modules')
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$source = @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

public sealed class AdvisorNtfsParent : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Info {
        public uint Attributes, CreationLow, CreationHigh, AccessLow, AccessHigh,
            WriteLow, WriteHigh, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [StructLayout(LayoutKind.Sequential)] struct Basic {
        public long Creation, Access, Write, Change;
        public uint Attributes;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern SafeFileHandle CreateFileW(string path, uint access, uint share,
        IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool GetFileInformationByHandleEx(SafeFileHandle handle, int kind,
        out Basic info, uint bytes);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool GetVolumeInformationByHandleW(SafeFileHandle handle,
        StringBuilder name, uint nameSize, out uint serial, out uint maximum,
        out uint flags, StringBuilder filesystem, uint filesystemSize);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle,
        StringBuilder path, uint size, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
    static extern uint GetDriveTypeW(string root);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr FindFirstFileNameW(string path, uint flags,
        ref uint length, StringBuilder name);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool FindNextFileNameW(IntPtr search, ref uint length, StringBuilder name);
    [DllImport("kernel32.dll")] static extern bool FindClose(IntPtr search);
    [DllImport("advapi32.dll", SetLastError=true)]
    static extern uint GetSecurityInfo(SafeFileHandle handle, int kind, uint sections,
        out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl,
        out IntPtr descriptor);
    [DllImport("advapi32.dll")] static extern uint GetSecurityDescriptorLength(IntPtr descriptor);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);

    readonly string path, root, sid;
    SafeFileHandle fileHandle, rootHandle;
    static ulong Id(Info value) { return ((ulong)value.IndexHigh << 32) | value.IndexLow; }
    static ulong Size(Info value) { return ((ulong)value.SizeHigh << 32) | value.SizeLow; }
    static Info Information(SafeFileHandle handle) {
        Info value;
        if (!GetFileInformationByHandle(handle, out value)) throw new InvalidOperationException("identity");
        return value;
    }
    static SafeFileHandle Open(string name, bool directory) {
        SafeFileHandle handle = CreateFileW(name, 0x20080, 7, IntPtr.Zero, 3,
            0x00200000U | (directory ? 0x02000000U : 0), IntPtr.Zero);
        if (handle.IsInvalid) { handle.Dispose(); throw new InvalidOperationException("open"); }
        return handle;
    }
    static void RequirePath(SafeFileHandle handle, string expected, bool directory) {
        Info value = Information(handle);
        if ((value.Attributes & 0x400) != 0 || ((value.Attributes & 0x10) != 0) != directory)
            throw new InvalidOperationException("reparse_or_type");
        StringBuilder final = new StringBuilder(32768);
        uint length = GetFinalPathNameByHandleW(handle, final, 32768, 0);
        if (length == 0 || length >= 32768) throw new InvalidOperationException("path");
        string observed = final.ToString();
        if (!observed.StartsWith("\\\\?\\", StringComparison.Ordinal)) throw new InvalidOperationException("path");
        if (!String.Equals(observed.Substring(4), expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("path");
        using (SafeFileHandle reopened = Open(expected, directory)) {
            Info again = Information(reopened);
            if (again.Volume != value.Volume || Id(again) != Id(value))
                throw new InvalidOperationException("path_identity");
        }
    }
    string Security(SafeFileHandle handle) {
        IntPtr owner, group, dacl, sacl, descriptor;
        if (GetSecurityInfo(handle, 1, 5, out owner, out group, out dacl, out sacl, out descriptor) != 0)
            throw new InvalidOperationException("security");
        try {
            uint length = GetSecurityDescriptorLength(descriptor);
            if (length == 0 || length > 65536) throw new InvalidOperationException("security_size");
            byte[] bytes = new byte[length];
            Marshal.Copy(descriptor, bytes, 0, bytes.Length);
            RawSecurityDescriptor security = new RawSecurityDescriptor(bytes, 0);
            if (security.Owner == null || security.Owner.Value != sid || security.DiscretionaryAcl == null ||
                (security.ControlFlags & ControlFlags.DiscretionaryAclPresent) == 0)
                throw new InvalidOperationException("owner_or_acl");
            bool callerReads = false;
            const uint readOnly = 0xA01200A9U;
            foreach (GenericAce entry in security.DiscretionaryAcl) {
                if ((entry.AceFlags & AceFlags.InheritOnly) != 0) continue;
                CommonAce ace = entry as CommonAce;
                if (ace == null || ace.IsCallback || ace.AceQualifier != AceQualifier.AccessAllowed)
                    throw new InvalidOperationException("unsupported_acl");
                string principal = ace.SecurityIdentifier.Value;
                uint mask = unchecked((uint)ace.AccessMask);
                bool trusted = principal == sid || principal == "S-1-5-18" || principal == "S-1-5-32-544";
                if (!trusted && (mask & ~readOnly) != 0) throw new InvalidOperationException("untrusted_writer");
                if (principal == sid && (mask & (1U | 0x80000000U | 0x10000000U)) != 0) callerReads = true;
            }
            if (!callerReads) throw new InvalidOperationException("caller_access");
            using (SHA256 hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        } finally { LocalFree(descriptor); }
    }
    void RequireAliases() {
        StringBuilder name = new StringBuilder(32768);
        uint length = 32768;
        IntPtr search = FindFirstFileNameW(path, 0, ref length, name);
        if (search == new IntPtr(-1)) throw new InvalidOperationException("aliases");
        try {
            HashSet<string> names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            bool original = false;
            for (;;) {
                string alias = name.ToString();
                if (!String.Equals(Path.GetFileName(alias), Path.GetFileName(path), StringComparison.Ordinal) ||
                    !names.Add(alias) || names.Count > 2) throw new InvalidOperationException("alias_identity");
                original |= String.Equals(alias, path.Substring(2), StringComparison.OrdinalIgnoreCase);
                length = 32768;
                if (!FindNextFileNameW(search, ref length, name)) {
                    if (Marshal.GetLastWin32Error() != 38) throw new InvalidOperationException("alias_enumeration");
                    break;
                }
            }
            if (names.Count != 2 || !original) throw new InvalidOperationException("alias_count");
        } finally { FindClose(search); }
    }
    public AdvisorNtfsParent(string filePath, string sessionsRoot) {
        path = Path.GetFullPath(filePath); root = Path.GetFullPath(sessionsRoot);
        if (path.Length > 4000 || root.Length > 4000 || GetDriveTypeW(Path.GetPathRoot(path)) != 3 ||
            !String.Equals(Path.GetPathRoot(path), Path.GetPathRoot(root), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("local_drive");
        sid = WindowsIdentity.GetCurrent().User.Value;
        try { rootHandle = Open(root, true); fileHandle = Open(path, false); }
        catch { Dispose(); throw; }
    }
    public Dictionary<string, object> Snapshot() {
        RequirePath(rootHandle, root, true); RequirePath(fileHandle, path, false);
        Info first = Information(fileHandle), directory = Information(rootHandle);
        Basic before;
        if (!GetFileInformationByHandleEx(fileHandle, 0, out before, (uint)Marshal.SizeOf(typeof(Basic))))
            throw new InvalidOperationException("basic");
        StringBuilder filesystem = new StringBuilder(32);
        uint serial, maximum, flags;
        if (!GetVolumeInformationByHandleW(fileHandle, null, 0, out serial, out maximum, out flags, filesystem, 32) ||
            filesystem.ToString() != "NTFS" || (flags & 8) == 0 || serial != first.Volume || directory.Volume != serial || first.Links != 2)
            throw new InvalidOperationException("ntfs_or_links");
        string fileSecurity = Security(fileHandle), rootSecurity = Security(rootHandle);
        RequireAliases();
        RequirePath(rootHandle, root, true); RequirePath(fileHandle, path, false);
        if (fileSecurity != Security(fileHandle) || rootSecurity != Security(rootHandle))
            throw new InvalidOperationException("security_changed");
        Info rootAgain = Information(rootHandle);
        Info last = Information(fileHandle);
        Basic basic;
        if (!GetFileInformationByHandleEx(fileHandle, 0, out basic, (uint)Marshal.SizeOf(typeof(Basic))) ||
            first.Volume != last.Volume || Id(first) != Id(last) || Size(first) != Size(last) ||
            first.Links != last.Links || first.WriteHigh != last.WriteHigh || first.WriteLow != last.WriteLow ||
            before.Change != basic.Change || before.Write != basic.Write ||
            directory.Volume != rootAgain.Volume || Id(directory) != Id(rootAgain))
            throw new InvalidOperationException("changed");
        return new Dictionary<string, object> {
            {"schema", 1}, {"ok", true}, {"file_id", Id(last).ToString()},
            {"root_id", Id(directory).ToString()}, {"volume", serial.ToString()},
            {"links", (int)last.Links}, {"size", Size(last).ToString()},
            {"mtime_ns", ((basic.Write - 116444736000000000L) * 100L).ToString()},
            {"change_time", basic.Change.ToString()}, {"file_security", fileSecurity},
            {"root_security", rootSecurity}, {"aliases", 2}, {"ntfs", true}, {"local", true}
        };
    }
    public void Dispose() {
        if (fileHandle != null) { fileHandle.Dispose(); fileHandle = null; }
        if (rootHandle != null) { rootHandle.Dispose(); rootHandle = null; }
    }
}
'@
$probe = $null
try {
    Add-Type -TypeDefinition $source -ErrorAction Stop
    $line = [Console]::In.ReadLine()
    if ($null -eq $line -or $line.Length -gt 8000) { throw 'request' }
    $request = $line | ConvertFrom-Json
    $probe = [AdvisorNtfsParent]::new([string]$request.path, [string]$request.root)
    [Console]::Out.WriteLine(($probe.Snapshot() | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
    $command = [Console]::In.ReadLine()
    if ($command -ceq 'recheck') {
        [Console]::Out.WriteLine(($probe.Snapshot() | ConvertTo-Json -Compress))
        [Console]::Out.Flush()
    }
} catch {
    [Console]::Out.WriteLine('{"schema":1,"ok":false}')
    [Console]::Out.Flush()
    exit 1
} finally {
    if ($null -ne $probe) { $probe.Dispose() }
}
