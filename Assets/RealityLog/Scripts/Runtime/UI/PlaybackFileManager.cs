# nullable enable

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using RealityLog.Common;

namespace RealityLog.UI
{
    /// <summary>
    /// Manages scanning and listing .glb mocap files available for playback.
    /// </summary>
    public class PlaybackFileManager : MonoBehaviour
    {
        [Header("Settings")]
        [Tooltip("Subdirectory under persistentDataPath where mocap_bridge pushes .glb files")]
        [SerializeField] private string playbackDirectoryName = "mocap_playback";

        private List<PlaybackFileInfo> files = new List<PlaybackFileInfo>();

        [Serializable]
        public class PlaybackFileInfo
        {
            public string FileName { get; set; } = string.Empty;
            public string FullPath { get; set; } = string.Empty;
            public DateTime CreationTime { get; set; }
            public long SizeBytes { get; set; }
            public string FormattedSize => FormatBytes(SizeBytes);
            public string FormattedDate => CreationTime.ToString("yyyy-MM-dd HH:mm:ss");

            private static string FormatBytes(long bytes)
            {
                string[] sizes = { "B", "KB", "MB", "GB" };
                double len = bytes;
                int order = 0;
                while (len >= 1024 && order < sizes.Length - 1)
                {
                    order++;
                    len = len / 1024;
                }
                return $"{len:0.##} {sizes[order]}";
            }
        }

        /// <summary>
        /// Event fired when the playback file list is updated.
        /// </summary>
        public event Action<List<PlaybackFileInfo>>? OnFilesUpdated;

        /// <summary>
        /// Gets the current list of playback files.
        /// </summary>
        public List<PlaybackFileInfo> Files => new List<PlaybackFileInfo>(files);

        public string PlaybackDirectoryPath => Path.Combine(Application.persistentDataPath, playbackDirectoryName);

        /// <summary>
        /// Scans the playback directory for .glb files.
        /// </summary>
        public void RefreshFiles()
        {
            files.Clear();

            try
            {
                string dirPath = PlaybackDirectoryPath;

                if (!Directory.Exists(dirPath))
                {
                    Debug.Log($"[{Constants.LOG_TAG}] PlaybackFileManager: Playback directory does not exist yet: {dirPath}");
                    OnFilesUpdated?.Invoke(files);
                    return;
                }

                foreach (var filePath in Directory.GetFiles(dirPath, "*.glb"))
                {
                    try
                    {
                        var info = new FileInfo(filePath);
                        files.Add(new PlaybackFileInfo
                        {
                            FileName = info.Name,
                            FullPath = filePath,
                            CreationTime = info.CreationTime,
                            SizeBytes = info.Length
                        });
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackFileManager: Error reading file {filePath}: {e.Message}");
                    }
                }

                files = files.OrderByDescending(f => f.CreationTime).ToList();

                Debug.Log($"[{Constants.LOG_TAG}] PlaybackFileManager: Found {files.Count} playback file(s)");
                OnFilesUpdated?.Invoke(files);
            }
            catch (Exception e)
            {
                Debug.LogError($"[{Constants.LOG_TAG}] PlaybackFileManager: Error scanning playback directory: {e.Message}");
                OnFilesUpdated?.Invoke(files);
            }
        }

        private void Start()
        {
            RefreshFiles();
        }
    }
}
