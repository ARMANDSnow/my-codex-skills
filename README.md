# My Codex Skills

Personal Codex skills repository.

## Install Or Update Skills

On another computer, clone this repository and run the installer:

```bash
git clone git@github.com:ARMANDSnow/my-codex-skills.git
cd my-codex-skills
./install.sh
```

The installer copies these skills into `~/.codex/skills/`:

- `resume-parser-hr`
- `hr-recruit-sop-qa`

Existing local copies with the same names are replaced, so `resume-parser-hr` will update to the latest version from this repository.

Restart Codex after installation.

## Update Later

```bash
cd my-codex-skills
git pull
./install.sh
```

If SSH is not configured on the computer, use HTTPS instead:

```bash
git clone https://github.com/ARMANDSnow/my-codex-skills.git
```
