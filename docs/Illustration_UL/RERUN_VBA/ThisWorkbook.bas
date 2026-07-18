Attribute VB_Name = "ThisWorkbook"
Attribute VB_Base = "0{00020819-0000-0000-C000-000000000046}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = True
Dim oProxy As Object



Public Sub AlertProxy(Optional EventID As Long)

On Error Resume Next

Set oProxy = CreateObject("Proxy.ExcelProxy")

oProxy.HandleControlEvents EventID

Set oProxy = Nothing

End Sub



Public Sub SaveWorkbook()

Set oProxy = CreateObject("Proxy.ExcelProxy")

oProxy.HandleControlEvents 1        ' 1 = write (upload), 2 = save (will cause error), 3 = read (download)

Set oProxy = Nothing

End Sub
