VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "AuditTab"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True


Private Sub GetPolicy_Click()
    GetPolicyInfo
    Range("mResults").Copy
    Range("sReproposal").PasteSpecial Paste:=xlPasteValues
End Sub


Private Sub GPBefore_Click()
    GuidelineCalcBeforeChange
End Sub

Private Sub GPAfter_Click()
    GuidelineCalcAfterChange
End Sub

Private Sub GPIssue_Click()
    GuidelineCalcIssue
End Sub
