# Optimistic Feedback ⚡

**Make your Home Assistant UI feel instantly responsive!**

> No more waiting for slow devices – get **instant visual feedback** the moment you tap any control, with automatic self-correction if the command fails.

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/nitaybz/optimistic_feedback)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nitaybz&repository=optimistic_feedback&category=integration)

## What does it do?

Home Assistant waits for devices to confirm state changes before updating the UI. This creates a noticeable delay, especially with:
- **Wi-Fi devices** (smart bulbs, switches)
- **Z-Wave/Zigbee devices** (dimmers, sensors)  
- **Cloud-based integrations** (smart assistants)

**Optimistic Feedback** predicts the outcome and updates the UI *instantly*, then self-corrects if needed when the real device responds.

### Before vs After
| **Before** | **After** |
|------------|-----------|
| Tap → Wait → UI updates | Tap → **Instant UI update** |
| Feels sluggish and unresponsive | Feels snappy and modern |
| Uncertainty if command worked | Immediate visual confirmation |

## Features

- **Instant UI updates** for lights, switches, covers, fans, and more
- **Smart toggle prediction** - knows current state and predicts correctly
- **Include/Exclude modes** - fine-tune which entities get optimistic feedback
- **Configurable debounce** - prevent UI flicker from rapid commands
- **7 languages supported** - English, Hebrew, Spanish, French, German, Italian, Portuguese
- **Self-healing** - automatically corrects if device command fails
- **Modern UI** - intuitive configuration with dynamic help text
- **Local only** - no cloud dependencies, zero privacy concerns

## Installation

### Via HACS (Recommended)
1. **Add Custom Repository:**
   - Go to **HACS → Integrations → ⋮ → Custom repositories**
   - URL: `https://github.com/nitaybz/optimistic_feedback`
   - Category: **Integration**

2. **Install:**
   - **HACS → Integrations → "Optimistic Feedback" → Download**

3. **Restart Home Assistant**

4. **Configure:**
   - **Settings → Devices & Services → Add Integration**
   - Search for **"Optimistic Feedback"**

### Manual Installation
1. Download the latest release
2. Copy `custom_components/optimistic_feedback` to your HA `custom_components` folder
3. Restart Home Assistant
4. Add the integration via UI

## Configuration

### Domains
Choose which device types get optimistic feedback:
- **light** - Smart bulbs, LED strips, dimmers
- **switch** - Smart switches, outlets, relays  
- **cover** - Blinds, curtains, garage doors
- **fan** - Ceiling fans, exhaust fans
- **climate** - Thermostats, AC units
- **media_player** - TVs, speakers, streaming devices
- **lock** - Smart locks, door locks

### Entity Filtering
**Two modes available:**

#### Include Mode (Selective)
- **Only** selected entities get optimistic feedback
- Perfect for testing or problematic devices
- More conservative approach

#### Exclude Mode (Default)  
- **All** domain entities get optimistic feedback **except** selected ones
- Good for excluding unreliable devices
- More comprehensive coverage

### Debounce Time
- **Default:** 400ms
- **Range:** 50-2000ms
- Prevents UI "bounce" from rapid state changes
- Lower = more responsive, Higher = more stable

## Supported Services

| Service | Predicted State | Notes |
|---------|----------------|-------|
| `turn_on` | `on` | Lights, switches, fans |
| `turn_off` | `off` | All domains |
| `toggle` | Smart prediction | Analyzes current state |
| `open_cover` | `open` | Blinds, garage doors |
| `close_cover` | `closed` | Blinds, garage doors |
| `set_cover_position` | `open`/`closed` | Based on position value |
| `media_play` | `playing` | Media players |
| `media_pause` | `paused` | Media players |
| `media_stop` | `idle` | Media players |
| `lock` | `locked` | Smart locks |
| `unlock` | `unlocked` | Smart locks |

## Advanced Features

### Race Condition Protection
- Prevents conflicts between optimistic and real state updates
- Smart state tracking prevents UI confusion
- Automatic recovery from failed predictions

### Debounce Intelligence  
- Entity-specific timing prevents rapid-fire updates
- Configurable timing for different use cases
- Prevents UI "wobble" during quick interactions

### Context-Aware Predictions
- **Toggle intelligence** - analyzes current state before prediction
- **Domain-specific logic** - different rules for different device types
- **Graceful fallbacks** - skips prediction for unknown services

## UI Improvements

- **Dynamic descriptions** that change based on your settings
- **Visual indicators** for include/exclude modes  
- **Real-time form updates** when switching modes
- **Helpful tooltips** explaining each option
- **Validation** with clear error messages

## Translations

Full UI translation support for:
- **English** - `en` 
- **Hebrew** - `he`
- **Spanish** - `es`
- **French** - `fr` 
- **German** - `de`
- **Italian** - `it`
- **Portuguese** - `pt`

## Limitations

- **Device failures:** If a device never responds, UI stays in optimistic state (same issue as before, just earlier)
- **Complex attributes:** Only state prediction, not attribute prediction (brightness, color, etc.)
- **Network commands:** Works best with local devices; cloud devices may have more latency

## Troubleshooting

### Integration not loading?
1. Check Home Assistant logs for errors
2. Ensure all files are in the correct folder
3. Restart Home Assistant completely

### UI not updating instantly?
1. Verify entity is in selected domains
2. Check include/exclude configuration  
3. Adjust debounce time if needed
4. Enable debug logging for detailed info

### Wrong state predictions?
1. Check device supports the service
2. Verify entity current state is accurate
3. Some devices may need custom logic

## Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.optimistic_feedback: debug
```

## Contributing

Found a bug? Have a feature request? 

1. **Issues:** [GitHub Issues](https://github.com/nitaybz/optimistic_feedback/issues)
2. **Discussions:** [GitHub Discussions](https://github.com/nitaybz/optimistic_feedback/discussions)  
3. **Pull Requests:** Always welcome!

## License

MIT License - see [LICENSE](LICENSE) file.

## Like this integration?

If Optimistic Feedback makes your Home Assistant experience better, consider:
- **⭐ Starring** this repository  
- **🐛 Reporting issues** to help improve it
- **💡 Suggesting features** for future versions
- **📢 Sharing** with other HA users

## Support Development

If you find this integration useful and want to support its continued development:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/nitaybz)

**Other ways to support:**
- 🅿️ [Patreon](https://patreon.com/nitaybz)
- 💳 [PayPal](https://paypal.me/nitaybz)
- ⭐ Star this repository
- 🗣️ Share with the community

Your support helps maintain this project and develop new features! 🚀

---

**Made with ❤️ for the Home Assistant community**
