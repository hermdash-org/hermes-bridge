
systemctl --user stop hermes-runtime.service

systemctl --user start hermes-runtime.service


Or to restart (stop + start in one):

systemctl --user restart hermes-runtime.service




# Incase of an update restart immediately to grab the new build
systemctl --user restart hermes-runtime.service
