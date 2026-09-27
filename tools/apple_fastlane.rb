#!/usr/bin/env ruby
# Create the App Store Connect app record + the APNs key with fastlane's spaceship (Apple ID login, no browser).
#
# Why (09/27/2026): Apple's API spec v4.5 has /v1/apps GET-only and no key/push-cert endpoint, so no API key can do
# either step. Headless AND headed Chrome both stalled after the password (Apple never sent /signin/complete).
# spaceship speaks Apple's sign-in protocol directly (signin/init -> complete + hashcash), same as fastlane produce.
# Joe: "see if there is a way to do this vis api etc or a special key".
#
# Creds: Joe drops T:\apple.txt (line1 Apple ID, line2 password) -> moved to tmpfs 0600, T: copy shredded.
# 2FA:   Joe drops the 6 digits in T:\apple-2fa.txt -> read, shredded.
# Out:   ~/secure/apple/ios/AuthKey_<KEYID>.p8 (0600) - the key is downloadable ONCE; never printed.
# Run:   GEM_HOME=~/.local/share/fastlane-gems ruby tools/apple_fastlane.rb      (log: $XDG_RUNTIME_DIR/apple/run.log)
require "fileutils"
RUN   = File.join(ENV.fetch("XDG_RUNTIME_DIR", "/run/user/1000"), "apple")
LOG   = File.join(RUN, "run.log")
SHARE = "/mnt/fs01-transfer"
TEAM  = "V829EBE8HH"
BUNDLE, NAME, SKU, KEYNAME = "com.wa0o.piauthenticator", "WA0O Auth", "wa0o-piauth", "WA0O push"
FileUtils.mkdir_p(RUN, mode: 0o700)
ENV["SPACESHIP_COOKIE_PATH"] = RUN          # session cookie on tmpfs, deleted at the end
ENV["FASTLANE_SKIP_UPDATE_CHECK"] = ENV["FASTLANE_OPT_OUT_USAGE"] = "1"

def log(*a) = File.open(LOG, "a") { |f| f.puts(Time.now.strftime("%H:%M:%S ") + a.join(" ")) }

def wait_file(path, mins)
  (mins * 60).times { return true if File.exist?(path) && File.size(path) > 5; sleep 1 }
  false
end

cred = File.join(RUN, "apple.txt")
unless File.exist?(cred)
  log "waiting for T:\\apple.txt"
  wait_file("#{SHARE}/apple.txt", 30) or (log "no apple.txt within 30 min"; exit 1)
  sleep 2
  system("install", "-m", "600", "#{SHARE}/apple.txt", cred, exception: true)
  system("shred", "-u", "#{SHARE}/apple.txt")
  log "apple.txt moved to tmpfs, T: copy shredded"
end
user, pw = File.read(cred).lines.map(&:strip)

require "spaceship"
# The 2FA prompt normally reads the terminal - read Joe's file instead.
module Spaceship
  class Client
    def ask_for_2fa_code(_text)
      File.delete("#{SHARE}/apple-2fa.txt") rescue nil   # a stale code from an earlier run is never used
      log "2FA requested - waiting for Joe's code in T:\\apple-2fa.txt"
      wait_file("#{SHARE}/apple-2fa.txt", 15) or raise "no 2FA code within 15 min"
      sleep 1
      code = File.read("#{SHARE}/apple-2fa.txt").scan(/\d/).join[0, 6]
      system("shred", "-u", "#{SHARE}/apple-2fa.txt")
      log "2FA code read (#{code.length} digits), file shredded"
      code
    end
  end
end

begin
  Spaceship::ConnectAPI.login(user, pw, portal_team_id: TEAM)
  log "SIGNED IN (App Store Connect + developer portal)"
  pw = nil

  app = Spaceship::ConnectAPI::App.find(BUNDLE)
  if app
    log "app record already exists: #{app.name} id #{app.id}"
  else
    Spaceship::ConnectAPI::App.create(name: NAME, version_string: "1.0", sku: SKU, primary_locale: "en-US",
                                      bundle_id: BUNDLE, platforms: ["IOS"])
    app = Spaceship::ConnectAPI::App.find(BUNDLE)
    log(app ? "APP CREATED: #{app.name} id #{app.id}" : "app create returned but find() sees nothing")
  end

  # ConnectAPI.login above also logged in Spaceship::Portal and selected team TEAM
  existing = Spaceship::Portal::Key.all.select { |k| k.name == KEYNAME }
  if existing.any?
    log "key '#{KEYNAME}' already exists: #{existing.map(&:id).join(',')} (a .p8 can only be downloaded once - not re-created)"
  else
    key = Spaceship::Portal::Key.create(name: KEYNAME, apns: true)
    out = File.expand_path("~/secure/apple/ios/AuthKey_#{key.id}.p8")
    File.open(out, File::WRONLY | File::CREAT | File::EXCL, 0o600) { |f| f.write(key.download) }
    log "APNS KEY CREATED: id #{key.id}, saved #{out} (0600)"
  end
rescue StandardError => e
  log "ERROR #{e.class}: #{e.message.to_s[0, 300]}"
ensure
  system("shred", "-u", cred) if File.exist?(cred)
  FileUtils.rm_rf(File.join(RUN, "spaceship"))
  log "creds + session cookie removed; done"
end
