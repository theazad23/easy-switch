-- Gaming Mode on NVIDIA + 4K TV: the screen sometimes showed torn bands and
-- stale blocks of earlier frames (scanout racing the GPU). Turn off gamescope's
-- explicit-sync path on the DRM backend so it waits for frames the old way.
gamescope.convars.drm_debug_disable_explicit_sync.value = true
warn("50-nvidia-tv-fix: drm_debug_disable_explicit_sync = " .. tostring(gamescope.convars.drm_debug_disable_explicit_sync.value))
