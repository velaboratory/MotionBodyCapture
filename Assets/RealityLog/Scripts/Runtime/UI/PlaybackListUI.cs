# nullable enable

using System.Collections.Generic;
using System.IO;
using UnityEngine;
using TMPro;
using RealityLog.Common;
using RealityLog.Playback;

namespace RealityLog.UI
{
    /// <summary>
    /// Main UI component that manages the playback file list display and loading.
    /// </summary>
    public class PlaybackListUI : MonoBehaviour
    {
        [Header("References")]
        [Tooltip("PlaybackFileManager to get the list of .glb files")]
        [SerializeField] private PlaybackFileManager fileManager = default!;

        [Tooltip("GlbAvatarLoader that performs the actual load/instantiate/play")]
        [SerializeField] private GlbAvatarLoader avatarLoader = default!;

        [Header("UI Elements")]
        [Tooltip("Container/ScrollView content for playback list items")]
        [SerializeField] private Transform listContainer = default!;

        [Tooltip("Prefab for playback list item UI")]
        [SerializeField] private GameObject playbackItemPrefab = default!;

        [Tooltip("Text component to show when no playback files are found")]
        [SerializeField] private GameObject emptyListMessage = default!;

        [Tooltip("Text component to show load status/feedback")]
        [SerializeField] private TextMeshProUGUI statusText = default!;

        private List<PlaybackListItemUI> itemInstances = new List<PlaybackListItemUI>();
        private Coroutine? statusHideCoroutine;

        private void OnEnable()
        {
            if (fileManager != null)
            {
                fileManager.OnFilesUpdated += OnFilesUpdated;
            }

            if (avatarLoader != null)
            {
                avatarLoader.OnLoaded += HandleLoaded;
                avatarLoader.OnLoadFailed += HandleLoadFailed;
            }

            if (statusText != null)
            {
                statusText.text = string.Empty;
            }

            RefreshList();
        }

        private void OnDisable()
        {
            if (fileManager != null)
            {
                fileManager.OnFilesUpdated -= OnFilesUpdated;
            }

            if (avatarLoader != null)
            {
                avatarLoader.OnLoaded -= HandleLoaded;
                avatarLoader.OnLoadFailed -= HandleLoadFailed;
            }
        }

        /// <summary>
        /// Refreshes the playback file list.
        /// </summary>
        public void RefreshList()
        {
            if (fileManager != null)
            {
                fileManager.RefreshFiles();
            }
        }

        private void OnFilesUpdated(List<PlaybackFileManager.PlaybackFileInfo> files)
        {
            Debug.Log($"[{Constants.LOG_TAG}] PlaybackListUI: OnFilesUpdated called with {files.Count} file(s)");

            foreach (var item in itemInstances)
            {
                if (item != null)
                    Destroy(item.gameObject);
            }
            itemInstances.Clear();

            if (emptyListMessage != null)
            {
                emptyListMessage.SetActive(files.Count == 0);
            }

            if (playbackItemPrefab == null)
            {
                Debug.LogError($"[{Constants.LOG_TAG}] PlaybackListUI: playbackItemPrefab is null!");
                return;
            }

            if (listContainer == null)
            {
                Debug.LogError($"[{Constants.LOG_TAG}] PlaybackListUI: listContainer is null!");
                return;
            }

            foreach (var file in files)
            {
                var itemObj = Instantiate(playbackItemPrefab, listContainer);
                var itemUI = itemObj.GetComponent<PlaybackListItemUI>();

                if (itemUI != null)
                {
                    itemUI.SetFile(file);
                    itemUI.OnPlayClicked += HandlePlayClicked;
                    itemInstances.Add(itemUI);
                }
                else
                {
                    Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackListUI: Prefab doesn't have PlaybackListItemUI component!");
                }
            }
        }

        private void HandlePlayClicked(string filePath)
        {
            if (avatarLoader != null)
            {
                ShowStatus($"Loading {Path.GetFileName(filePath)}...", true, 1000f);
                avatarLoader.LoadAndPlay(filePath);
            }
        }

        private void HandleLoaded(GameObject avatar)
        {
            ShowStatus($"Playing {avatar.name}", true);
        }

        private void HandleLoadFailed(string filePath)
        {
            ShowStatus($"Failed to load {Path.GetFileName(filePath)}", false);
        }

        private void ShowStatus(string message, bool isSuccess, float duration = 5f)
        {
            if (statusText != null)
            {
                statusText.text = message;
                statusText.color = isSuccess ? Color.green : Color.red;

                if (statusHideCoroutine != null)
                {
                    StopCoroutine(statusHideCoroutine);
                }
                statusHideCoroutine = StartCoroutine(HideStatusAfterDelay(duration));
            }
        }

        private System.Collections.IEnumerator HideStatusAfterDelay(float delay)
        {
            yield return new WaitForSeconds(delay);
            if (statusText != null)
            {
                statusText.text = string.Empty;
            }
            statusHideCoroutine = null;
        }

        private void OnValidate()
        {
            if (fileManager == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackListUI: Missing PlaybackFileManager reference!");

            if (avatarLoader == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackListUI: Missing GlbAvatarLoader reference!");

            if (listContainer == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackListUI: Missing list container Transform reference!");

            if (playbackItemPrefab == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackListUI: Missing playback item prefab reference!");
        }
    }
}
