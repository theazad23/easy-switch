-- Gaming Mode on NVIDIA + 4K TV: the screen sometimes showed torn bands and
-- stale blocks of earlier frames (scanout racing the GPU). Turn off gamescope's
-- explicit-sync path on the DRM backend so it waits for frames the old way.
gamescope.convars.drm_debug_disable_explicit_sync.value = true
(warn or print)("50-nvidia-tv-fix: drm_debug_disable_explicit_sync = " .. tostring(gamescope.convars.drm_debug_disable_explicit_sync.value))

-- GBM scan-out buffers (only exists in GBM-patched gamescope builds; stock ignores this).
-- NVIDIA can't scan out non-contiguous memory; Vulkan-allocated 4K buffers sometimes are.
local gbm = gamescope.convars.drm_gbm_scanout
if gbm then
    gbm.value = true
    ;(warn or print)("50-nvidia-tv-fix: drm_gbm_scanout = " .. tostring(gbm.value))
end
