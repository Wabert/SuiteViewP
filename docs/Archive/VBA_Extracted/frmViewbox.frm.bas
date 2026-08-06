' Module: frmViewbox.frm
' Type: Standard Module
' Stream Path: VBA/frmViewbox
' =========================================================

Attribute VB_Name = "frmViewbox"
Attribute VB_Base = "0{0203B0FA-F462-4EC9-A0F7-94F7406D15D4}{F4357470-2A59-494D-8D49-D4C508025C86}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False






Public Sub Initialize()

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Date"
s.AddColumn "PolicyYear"
s.AddColumn "Month"


For X = 1 To 100
    s.AddRow
    s("Date") = DateAdd("m", X, #1/5/2018#)
    s("PolicyYear") = 2
    s("Month") = 5 + X
Next

'Dim FB As cls_FilterBox
'Set FB = New cls_FilterBox
'
'FB.ClassInitialize frViewBox1, s.GetArrayOfValues


Dim VBox As clsVBox
Set VBox = New clsVBox

VBox.Initialize Me.frViewBox1
VBox.TableData = s.GetArrayOfValues




End Sub

Public Sub testheight()


Dim ary()
k = 2000

ReDim ary(k)

For X = 0 To k
    ary(X) = X
Next

ListBox1.Font.Size = 8
ListBox1.ColumnWidths = "1"



With ListBox1

    .List = ary

    .height = .ListCount * 9.75 + 9.75   '(PointsToPixels(.Font.Size))

End With


FrameTest.ScrollBars = fmScrollBarsVertical
FrameTest.ScrollHeight = ListBox1.height + 2


End Sub


