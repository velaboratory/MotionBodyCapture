# nullable enable

using UnityEngine;
using UnityEngine.UI;
using RealityLog.Common;

namespace RealityLog.UI
{
    /// <summary>
    /// Switches between the Recordings and Playback panels within the recording menu.
    /// </summary>
    public class MenuTabController : MonoBehaviour
    {
        [Header("Panels")]
        [SerializeField] private GameObject recordingsPanel = default!;
        [SerializeField] private GameObject playbackPanel = default!;

        [Header("Tab Buttons")]
        [SerializeField] private Button recordingsTabButton = default!;
        [SerializeField] private Button playbackTabButton = default!;

        private void Awake()
        {
            if (recordingsTabButton != null)
                recordingsTabButton.onClick.AddListener(ShowRecordingsTab);

            if (playbackTabButton != null)
                playbackTabButton.onClick.AddListener(ShowPlaybackTab);
        }

        private void OnEnable()
        {
            ShowRecordingsTab();
        }

        public void ShowRecordingsTab()
        {
            if (recordingsPanel != null) recordingsPanel.SetActive(true);
            if (playbackPanel != null) playbackPanel.SetActive(false);
        }

        public void ShowPlaybackTab()
        {
            if (recordingsPanel != null) recordingsPanel.SetActive(false);
            if (playbackPanel != null) playbackPanel.SetActive(true);
        }

        private void OnValidate()
        {
            if (recordingsPanel == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] MenuTabController: Missing recordingsPanel reference!");
            if (playbackPanel == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] MenuTabController: Missing playbackPanel reference!");
        }
    }
}
