# nullable enable

using System;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace RealityLog.UI
{
    /// <summary>
    /// UI component representing a single playback (.glb) file in the list.
    /// </summary>
    public class PlaybackListItemUI : MonoBehaviour
    {
        [Header("UI Elements")]
        [Tooltip("Text component displaying the file name")]
        [SerializeField] private TextMeshProUGUI fileNameText = default!;

        [Tooltip("Text component displaying the file date/time")]
        [SerializeField] private TextMeshProUGUI dateText = default!;

        [Tooltip("Text component displaying the file size")]
        [SerializeField] private TextMeshProUGUI sizeText = default!;

        [Header("Buttons")]
        [Tooltip("Button to load and play this avatar")]
        [SerializeField] private Button playButton = default!;

        private string filePath = string.Empty;

        /// <summary>
        /// Event fired when play button is clicked. Passes the full file path.
        /// </summary>
        public event Action<string>? OnPlayClicked;

        private void Awake()
        {
            if (playButton != null)
                playButton.onClick.AddListener(() => OnPlayClicked?.Invoke(filePath));
        }

        /// <summary>
        /// Sets the playback file information to display.
        /// </summary>
        public void SetFile(PlaybackFileManager.PlaybackFileInfo info)
        {
            filePath = info.FullPath;

            if (fileNameText != null)
                fileNameText.text = info.FileName;

            if (dateText != null)
                dateText.text = info.FormattedDate;

            if (sizeText != null)
                sizeText.text = info.FormattedSize;
        }
    }
}
