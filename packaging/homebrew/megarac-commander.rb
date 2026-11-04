class MegaracCommander < Formula
  desc "Unified HTML5 iKVM & IPMI 2.0 Control Center for AMI MegaRAC SP"
  homepage "https://github.com/larslog3/megarac-commander"
  url "https://github.com/larslog3/megarac-commander/releases/download/v1.0.0/megarac-commander-1.0.0-linux-any.tar.gz"
  version "1.0.0"
  license "MIT"

  depends_on "ipmitool"
  depends_on "python@3.11"

  def install
    libexec.install "index.html", "bridge_server.py", "ModernJViewerBridge.java"
    (bin/"megarac-commander").write <<~EOS
      #!/bin/bash
      exec "#{Formula["python@3.11"].opt_bin}/python3" "#{libexec}/bridge_server.py" "$@"
    EOS
  end
end
