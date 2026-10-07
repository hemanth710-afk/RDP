$.writeln("IPC Test");
var file = new File("C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\test_out2.txt");
file.open("w"); file.write("IPC success"); file.close();
app.project.save(new File("C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\ipc_proj.aep"));
