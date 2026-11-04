import javax.swing.*;
import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.lang.reflect.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.List;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;

/**
 * ModernJViewerBridge:
 * Launches AMI MegaRAC SP JViewer.jar inside the same JVM, dynamically extracts
 * all Swing JMenuBar menus, JMenuItems, JToolBar buttons, and JViewerApp methods,
 * hides the legacy 2012 Java Swing chrome (menu bar, toolbar, window decorations)
 * so only the live server video canvas fills the screen, and exposes a local JSON
 * control API on 127.0.0.1:9099 so the modern web app can trigger any JViewer
 * command natively from HTML5 controls.
 */
public class ModernJViewerBridge {
    private static volatile boolean chromelessMode = true;
    private static volatile String windowTitle = "Connecting to BMC JViewer...";
    private static volatile boolean jviewerWindowFound = false;
    private static final Map<String, AbstractButton> actionRegistry = new LinkedHashMap<String, AbstractButton>();
    private static final List<String> menuJsonEntries = new ArrayList<String>();
    private static final List<String> reflectedMethods = new ArrayList<String>();
    private static JFrame mainJViewerFrame = null;

    public static void main(String[] args) throws Exception {
        startControlHttpServer();
        inspectReflectedClasses();
        startSwingWatcherTimer();

        System.out.println("[ModernJViewerBridge] Invoking com.ami.kvm.jviewer.JViewer.main with args: " + Arrays.toString(args));
        Class<?> jviewerClass = Class.forName("com.ami.kvm.jviewer.JViewer");
        Method mainMethod = jviewerClass.getMethod("main", String[].class);
        mainMethod.invoke(null, (Object) args);
    }

    private static void inspectReflectedClasses() {
        String[] targetClasses = new String[] {
            "com.ami.kvm.jviewer.JViewer",
            "com.ami.kvm.jviewer.gui.JViewerApp",
            "com.ami.kvm.jviewer.gui.JVMenu",
            "com.ami.kvm.jviewer.kvmpkts.KVMClient"
        };
        for (String clsName : targetClasses) {
            try {
                Class<?> cls = Class.forName(clsName);
                for (Method m : cls.getDeclaredMethods()) {
                    if (Modifier.isPublic(m.getModifiers())) {
                        reflectedMethods.add(cls.getSimpleName() + "." + m.getName() + "(" + m.getParameterTypes().length + " args)");
                    }
                }
            } catch (Throwable ignored) {}
        }
    }

    private static void startSwingWatcherTimer() {
        javax.swing.Timer timer = new javax.swing.Timer(800, new ActionListener() {
            @Override
            public void actionPerformed(ActionEvent e) {
                try {
                    scanAndModernizeWindows();
                } catch (Throwable t) {
                    // Ignore transient Swing hierarchy changes
                }
            }
        });
        timer.setRepeats(true);
        timer.start();
    }

    private static void scanAndModernizeWindows() {
        Window[] windows = Window.getWindows();
        for (Window w : windows) {
            if (!w.isShowing()) continue;
            if (w instanceof JFrame) {
                JFrame jf = (JFrame) w;
                String t = jf.getTitle() != null ? jf.getTitle() : "";
                if (jf.getJMenuBar() != null || t.toLowerCase().contains("jviewer") || t.toLowerCase().contains("kvm") || mainJViewerFrame == null) {
                    mainJViewerFrame = jf;
                    jviewerWindowFound = true;
                    if (!t.isEmpty()) {
                        windowTitle = t;
                    }
                    extractMenusAndToolbars(jf);
                    applyChromelessLayout(jf);
                }
            } else if (w instanceof JDialog) {
                JDialog jd = (JDialog) w;
                if (jd.getWidth() > 50 && jd.getHeight() > 50) {
                    int x = Math.max(0, (1280 - jd.getWidth()) / 2);
                    int y = Math.max(0, (800 - jd.getHeight()) / 2);
                    if (jd.getX() == 0 && jd.getY() == 0) {
                        jd.setLocation(x, y);
                    }
                    jd.toFront();
                }
            }
        }
    }

    private static void extractMenusAndToolbars(JFrame jf) {
        Map<String, AbstractButton> nextReg = new LinkedHashMap<String, AbstractButton>();
        List<String> nextJson = new ArrayList<String>();

        JMenuBar mb = jf.getJMenuBar();
        if (mb != null) {
            for (int i = 0; i < mb.getMenuCount(); i++) {
                JMenu menu = mb.getMenu(i);
                if (menu == null) continue;
                String topName = cleanText(menu.getText());
                if (topName.isEmpty()) continue;
                walkMenuComponent(topName, menu, nextReg, nextJson);
            }
        }

        List<JToolBar> toolbars = new ArrayList<JToolBar>();
        findComponentsByType(jf.getContentPane(), JToolBar.class, toolbars);
        for (JToolBar tb : toolbars) {
            for (Component c : tb.getComponents()) {
                if (c instanceof AbstractButton) {
                    AbstractButton b = (AbstractButton) c;
                    String label = cleanText(b.getText());
                    if (label.isEmpty() && b.getToolTipText() != null) {
                        label = cleanText(b.getToolTipText());
                    }
                    if (label.isEmpty() && b.getActionCommand() != null) {
                        label = cleanText(b.getActionCommand());
                    }
                    if (!label.isEmpty()) {
                        String id = "Toolbar::" + label;
                        nextReg.put(id, b);
                        nextJson.add(buildItemJson(id, "Toolbar", label, b));
                    }
                }
            }
        }

        synchronized (actionRegistry) {
            actionRegistry.clear();
            actionRegistry.putAll(nextReg);
            menuJsonEntries.clear();
            menuJsonEntries.addAll(nextJson);
        }
    }

    private static void walkMenuComponent(String category, JMenu menu, Map<String, AbstractButton> reg, List<String> jsonList) {
        for (int i = 0; i < menu.getItemCount(); i++) {
            JMenuItem item = menu.getItem(i);
            if (item == null) continue;
            if (item instanceof JMenu) {
                JMenu sub = (JMenu) item;
                String subName = cleanText(sub.getText());
                walkMenuComponent(category + " > " + subName, sub, reg, jsonList);
            } else {
                String label = cleanText(item.getText());
                if (label.isEmpty()) continue;
                String id = category + "::" + label;
                reg.put(id, item);
                jsonList.add(buildItemJson(id, category, label, item));
            }
        }
    }

    private static String buildItemJson(String id, String category, String label, AbstractButton btn) {
        String type = "action";
        if (btn instanceof JCheckBoxMenuItem || btn instanceof JToggleButton) {
            type = "checkbox";
        } else if (btn instanceof JRadioButtonMenuItem) {
            type = "radio";
        }
        return String.format(
            "{\"id\":\"%s\",\"category\":\"%s\",\"label\":\"%s\",\"type\":\"%s\",\"selected\":%s,\"enabled\":%s}",
            esc(id), esc(category), esc(label), type, btn.isSelected(), btn.isEnabled()
        );
    }

    private static void applyChromelessLayout(JFrame jf) {
        JMenuBar mb = jf.getJMenuBar();
        if (mb != null && mb.isVisible() == chromelessMode) {
            mb.setVisible(!chromelessMode);
        }

        List<JToolBar> toolbars = new ArrayList<JToolBar>();
        findComponentsByType(jf.getContentPane(), JToolBar.class, toolbars);
        for (JToolBar tb : toolbars) {
            if (tb.isVisible() == chromelessMode) {
                tb.setVisible(!chromelessMode);
            }
        }

        if (jf.getWidth() < 1260 || jf.getHeight() < 760 || jf.getX() != 0 || jf.getY() != 0) {
            jf.setExtendedState(JFrame.MAXIMIZED_BOTH);
            jf.setBounds(0, 0, 1280, 800);
            jf.validate();
        }
    }

    private static <T extends Component> void findComponentsByType(Container root, Class<T> cls, List<T> out) {
        for (Component c : root.getComponents()) {
            if (cls.isInstance(c)) {
                out.add(cls.cast(c));
            }
            if (c instanceof Container) {
                findComponentsByType((Container) c, cls, out);
            }
        }
    }

    private static String cleanText(String s) {
        if (s == null) return "";
        return s.replaceAll("[\\r\\n\\t]+", " ").trim();
    }

    private static String esc(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static void startControlHttpServer() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 9099), 0);

        server.createContext("/state", new HttpHandler() {
            @Override
            public void handle(HttpExchange ex) throws IOException {
                StringBuilder sb = new StringBuilder();
                sb.append("{");
                sb.append("\"ok\":true,");
                sb.append("\"windowFound\":").append(jviewerWindowFound).append(",");
                sb.append("\"chromeless\":").append(chromelessMode).append(",");
                sb.append("\"windowTitle\":\"").append(esc(windowTitle)).append("\",");
                synchronized (actionRegistry) {
                    sb.append("\"items\":[").append(String.join(",", menuJsonEntries)).append("],");
                }
                List<String> mJson = new ArrayList<String>();
                int limit = Math.min(80, reflectedMethods.size());
                for (int i = 0; i < limit; i++) {
                    mJson.add("\"" + esc(reflectedMethods.get(i)) + "\"");
                }
                sb.append("\"methods\":[").append(String.join(",", mJson)).append("]");
                sb.append("}");

                byte[] bytes = sb.toString().getBytes(StandardCharsets.UTF_8);
                ex.getResponseHeaders().set("Content-Type", "application/json");
                ex.sendResponseHeaders(200, bytes.length);
                OutputStream os = ex.getResponseBody();
                os.write(bytes);
                os.close();
            }
        });

        server.createContext("/click", new HttpHandler() {
            @Override
            public void handle(HttpExchange ex) throws IOException {
                String query = ex.getRequestURI().getQuery() != null ? ex.getRequestURI().getQuery() : "";
                String target = URLDecoder.decode(query.replace("id=", ""), "UTF-8").trim();
                final boolean[] clicked = new boolean[] { false };
                final String[] matchedLabel = new String[] { "" };

                try {
                    SwingUtilities.invokeAndWait(new Runnable() {
                        @Override
                        public void run() {
                            AbstractButton btn = null;
                            synchronized (actionRegistry) {
                                btn = actionRegistry.get(target);
                                if (btn == null) {
                                    String lower = target.toLowerCase();
                                    for (Map.Entry<String, AbstractButton> entry : actionRegistry.entrySet()) {
                                        if (entry.getKey().toLowerCase().contains(lower) || cleanText(entry.getValue().getText()).toLowerCase().contains(lower)) {
                                            btn = entry.getValue();
                                            break;
                                        }
                                    }
                                }
                            }
                            if (btn != null) {
                                btn.doClick();
                                clicked[0] = true;
                                matchedLabel[0] = cleanText(btn.getText());
                            }
                        }
                    });
                } catch (Exception ignored) {}

                String resp = String.format("{\"ok\":%s,\"clicked\":\"%s\"}", clicked[0], esc(matchedLabel[0]));
                byte[] bytes = resp.getBytes(StandardCharsets.UTF_8);
                ex.getResponseHeaders().set("Content-Type", "application/json");
                ex.sendResponseHeaders(200, bytes.length);
                OutputStream os = ex.getResponseBody();
                os.write(bytes);
                os.close();
            }
        });

        server.createContext("/chrome", new HttpHandler() {
            @Override
            public void handle(HttpExchange ex) throws IOException {
                String q = ex.getRequestURI().getQuery() != null ? ex.getRequestURI().getQuery() : "";
                chromelessMode = !q.contains("false");
                try {
                    SwingUtilities.invokeLater(new Runnable() {
                        @Override
                        public void run() {
                            if (mainJViewerFrame != null) {
                                applyChromelessLayout(mainJViewerFrame);
                            }
                        }
                    });
                } catch (Exception ignored) {}
                String resp = String.format("{\"ok\":true,\"chromeless\":%s}", chromelessMode);
                byte[] bytes = resp.getBytes(StandardCharsets.UTF_8);
                ex.getResponseHeaders().set("Content-Type", "application/json");
                ex.sendResponseHeaders(200, bytes.length);
                OutputStream os = ex.getResponseBody();
                os.write(bytes);
                os.close();
            }
        });

        server.setExecutor(null);
        server.start();
        System.out.println("[ModernJViewerBridge] Control API listening on http://127.0.0.1:9099");
    }
}
