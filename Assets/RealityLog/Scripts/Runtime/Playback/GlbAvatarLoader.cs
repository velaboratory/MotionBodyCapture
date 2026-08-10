# nullable enable

using System;
using UnityEngine;
using GLTFast;
using RealityLog.Common;

namespace RealityLog.Playback
{
    /// <summary>
    /// Loads a .glb file at runtime via glTFast, places it in front of the
    /// player (world-space, not head-locked), and plays its first animation
    /// clip (if any).
    /// </summary>
    public class GlbAvatarLoader : MonoBehaviour
    {
        [Header("References")]
        [Tooltip("Camera transform to spawn avatars in front of (e.g., OVRCameraRig.CenterEyeAnchor)")]
        [SerializeField] private Transform cameraTransform = default!;

        [Header("Settings")]
        [Tooltip("Distance in front of camera (in meters)")]
        [SerializeField] private float distance = 2f;

        [Tooltip("Height offset from camera (in meters, positive = above eye level)")]
        [SerializeField] private float heightOffset = -1f;

        private GameObject? currentAvatar;

        public bool IsLoading { get; private set; }

        /// <summary>Fired with the file path when loading/instantiating fails.</summary>
        public event Action<string>? OnLoadFailed;

        /// <summary>Fired with the newly spawned avatar root once loaded and playing.</summary>
        public event Action<GameObject>? OnLoaded;

        /// <summary>
        /// Loads and plays the .glb at the given path, replacing any currently loaded avatar.
        /// </summary>
        public async void LoadAndPlay(string filePath)
        {
            if (IsLoading)
            {
                Debug.LogWarning($"[{Constants.LOG_TAG}] GlbAvatarLoader: Already loading, ignoring request for {filePath}");
                return;
            }

            IsLoading = true;

            try
            {
                ClearCurrentAvatar();

                var gltf = new GltfImport();
                bool loaded = await gltf.Load(new Uri(filePath));
                if (!loaded)
                {
                    Debug.LogError($"[{Constants.LOG_TAG}] GlbAvatarLoader: Failed to load {filePath}");
                    OnLoadFailed?.Invoke(filePath);
                    return;
                }

                var avatarRoot = new GameObject(System.IO.Path.GetFileNameWithoutExtension(filePath));
                PositionInFrontOfCamera(avatarRoot.transform);

                var instantiator = new GameObjectInstantiator(gltf, avatarRoot.transform);
                bool instantiated = await gltf.InstantiateMainSceneAsync(instantiator);
                if (!instantiated)
                {
                    Debug.LogError($"[{Constants.LOG_TAG}] GlbAvatarLoader: Failed to instantiate {filePath}");
                    Destroy(avatarRoot);
                    OnLoadFailed?.Invoke(filePath);
                    return;
                }

                currentAvatar = avatarRoot;
                PlayFirstClip(gltf, avatarRoot);

                Debug.Log($"[{Constants.LOG_TAG}] GlbAvatarLoader: Loaded and playing {filePath}");
                OnLoaded?.Invoke(avatarRoot);
            }
            catch (Exception e)
            {
                Debug.LogError($"[{Constants.LOG_TAG}] GlbAvatarLoader: Exception loading {filePath}: {e}");
                OnLoadFailed?.Invoke(filePath);
            }
            finally
            {
                IsLoading = false;
            }
        }

        private void PlayFirstClip(GltfImport gltf, GameObject avatarRoot)
        {
            var clips = gltf.GetAnimationClips();
            if (clips == null || clips.Length == 0)
            {
                Debug.LogWarning($"[{Constants.LOG_TAG}] GlbAvatarLoader: No animation clips found in glb");
                return;
            }

            var animation = avatarRoot.AddComponent<Animation>();
            foreach (var clip in clips)
            {
                clip.wrapMode = WrapMode.Loop;
                animation.AddClip(clip, clip.name);
            }
            animation.clip = clips[0];
            animation.Play(clips[0].name);
        }

        /// <summary>
        /// Removes the currently loaded avatar, if any.
        /// </summary>
        public void ClearCurrentAvatar()
        {
            if (currentAvatar != null)
            {
                Destroy(currentAvatar);
                currentAvatar = null;
            }
        }

        /// <summary>
        /// One-time world-space placement in front of the camera, matching
        /// WorldSpaceMenuPositioner's approach: the avatar is NOT parented to
        /// the camera rig, so it stays put in the room instead of following
        /// the player's head.
        /// </summary>
        private void PositionInFrontOfCamera(Transform avatarTransform)
        {
            Vector3 cameraPos = cameraTransform.position;
            Vector3 forward = cameraTransform.forward;
            Vector3 position = cameraPos + forward * distance;
            position.y += heightOffset;

            avatarTransform.position = position;

            Vector3 directionToCamera = cameraPos - position;
            directionToCamera.Normalize();
            directionToCamera.y = 0;
            directionToCamera.Normalize();

            if (directionToCamera != Vector3.zero)
            {
                avatarTransform.rotation = Quaternion.LookRotation(directionToCamera, Vector3.up);
            }
        }

        private void OnValidate()
        {
            if (cameraTransform == null)
                Debug.LogWarning($"[{Constants.LOG_TAG}] GlbAvatarLoader: Missing cameraTransform reference!");
        }
    }
}
