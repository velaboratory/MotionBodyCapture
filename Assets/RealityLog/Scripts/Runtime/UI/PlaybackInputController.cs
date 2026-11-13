# nullable enable

using UnityEngine;
using RealityLog.Common;
using RealityLog.Playback;

namespace RealityLog.UI
{
    /// <summary>
    /// Controller shortcuts for mocap playback, so it works without the menu:
    /// right A = play/pause, right B = restart from the first frame.
    /// Creates itself after the scene loads, so no scene edit is needed.
    /// </summary>
    public class PlaybackInputController : MonoBehaviour
    {
        private GlbAvatarLoader? loader;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void AutoCreate()
        {
            if (FindFirstObjectByType<PlaybackInputController>() != null) return;

            var go = new GameObject("PlaybackInputController");
            go.AddComponent<PlaybackInputController>();
        }

        private void Update()
        {
            if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
            {
                GetLoader()?.TogglePlayPause();
            }

            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch))
            {
                GetLoader()?.Restart();
            }
        }

        private GlbAvatarLoader? GetLoader()
        {
            if (loader == null)
            {
                loader = FindFirstObjectByType<GlbAvatarLoader>();
                if (loader == null)
                {
                    Debug.LogWarning($"[{Constants.LOG_TAG}] PlaybackInputController: no GlbAvatarLoader in the scene");
                }
            }
            return loader;
        }
    }
}
