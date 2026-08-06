' Module: cls_ControlEvents.cls
' Type: Class Module
' Stream Path: VBA/cls_ControlEvents
' =========================================================

Attribute VB_Name = "cls_ControlEvents"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private WithEvents cntLabel As MSForms.Label
Attribute cntLabel.VB_VarHelpID = -1
Private WithEvents cntTextBox As MSForms.textBox
Attribute cntTextBox.VB_VarHelpID = -1
Private WithEvents cntListBox As MSForms.Listbox
Attribute cntListBox.VB_VarHelpID = -1

Private mHelpTxt As MSForms.Label
Private MyControl As Object

Private mParentDataItem As Object

Public Sub classInitialize(objControl As Object, objDataItem As Object)
  Set cntLabel = objControl
 
  Set mParentDataItem = objDataItem
  Set MyControl = objControl
End Sub
Public Function GetControl() As MSForms.Label
  Set GetControl = cntLabel
End Function
Public Property Set HelpTextLabel(lbl As MSForms.Label)
  Set mHelpTxt = lbl
  With mHelpTxt
    .WordWrap = False
    .width = 200
    .caption = mParentDataItem.CommonName
    .Visible = False
    .Backcolor = ColorWhite
    .Font.Size = 12
    .AutoSize = True
    .AutoSize = False
    .width = mHelpTxt.width + 5
    .height = mHelpTxt.height + 2
    .BorderStyle = fmBorderStyleSingle
    .TextAlign = fmTextAlignCenter
  End With
End Property
Private Sub cntLabel_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
  mParentDataItem.DisplayDataCard
End Sub
Private Sub cntLabel_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
   mHelpTxt.top = Y + cntLabel.top - mHelpTxt.height - 10
   mHelpTxt.left = X + cntLabel.left - mHelpTxt.width / 2
   mHelpTxt.Visible = True
   cntLabel.Backcolor = cntLabel.Backcolor
End Sub
Private Sub cntLabel_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
  mHelpTxt.Visible = False
  cntLabel.Backcolor = cntLabel.Backcolor
End Sub

