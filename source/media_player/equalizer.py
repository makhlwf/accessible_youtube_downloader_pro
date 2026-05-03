import vlc


class EqualizerService:
    def __init__(self):
        self.equalizer = vlc.AudioEqualizer()
        self.preamp = 0.0

    def set_preamp(self, value):
        self.preamp = value
        self.equalizer.set_preamp(value)

    def set_band(self, index, value):
        self.equalizer.set_amp_at_index(value, index)

    def apply_to_player(self, player):
        player.set_equalizer(self.equalizer)
